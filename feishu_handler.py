"""飞书消息处理：长连接事件接收 + 消息回复。

采用飞书 WebSocket 长连接模式（免公网服务器 / 内网穿透）：
- 事件处理器 do_p2_im_message_receive_v1 由 SDK 分发回调
- 为避免飞书 3 秒超时重推，实际处理逻辑放到后台线程
- 通过 DifyClient 获取回答，再以卡片 / 文本消息回传
"""
from __future__ import annotations

import json
import logging
import re
import threading

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

from config import config
from conversation_store import ConversationStore
from dify_client import DifyClient, DifyReply

logger = logging.getLogger(__name__)

# 触发「重置上下文」的指令
RESET_KEYWORDS = {"新对话", "清除上下文", "重置", "/reset", "/new"}

# 消息去重集合（避免长连接重推导致重复回复）
_processed_message_ids: set[str] = set()
_processed_lock = threading.Lock()
_MAX_PROCESSED = 10000


def _mark_message_processed(message_id: str) -> bool:
    """返回 True 表示首次处理该消息；False 表示重复消息。"""
    if not message_id:
        return True
    with _processed_lock:
        if message_id in _processed_message_ids:
            return False
        if len(_processed_message_ids) >= _MAX_PROCESSED:
            _processed_message_ids.clear()
        _processed_message_ids.add(message_id)
        return True


def _extract_text(message) -> str:
    """从消息对象中提取纯文本，并去掉 @机器人 等提及占位符。"""
    raw = message.content or ""
    text = ""
    try:
        content = json.loads(raw)
        if isinstance(content, dict):
            text = content.get("text", "")
    except (json.JSONDecodeError, TypeError):
        text = raw

    # 依据 mentions 精确移除提及占位符（如 @_user_1）
    for mention in message.mentions or []:
        key = getattr(mention, "key", "")
        if key:
            text = text.replace(key, "")

    # 兜底：正则清理任何残留的提及占位符
    text = re.sub(r"@_user_\d+", "", text)
    text = re.sub(r"@_all", "", text)
    return text.strip()


def resolve_domain(name: str):
    """将 .env 中的域名配置映射为 lark SDK 的 Domain 对象。"""
    name = (name or "feishu").strip().lower()
    if name == "lark":
        return getattr(lark, "LARK_DOMAIN", None)
    return getattr(lark, "FEISHU_DOMAIN", None)


class FeishuClient:
    """负责向飞书发送消息（文本 / 卡片）。"""

    def __init__(self, app_id: str, app_secret: str, domain) -> None:
        builder = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.INFO)
        )
        if domain is not None:
            builder.domain(domain)
        self._client = builder.build()

    def send_text(self, chat_id: str, text: str) -> bool:
        content = json.dumps({"text": text}, ensure_ascii=False)
        return self._send(chat_id, "text", content)

    def send_card(self, chat_id: str, answer: str, note: str = "") -> bool:
        card = self._build_card(answer, note)
        content = json.dumps(card, ensure_ascii=False)
        return self._send(chat_id, "interactive", content)

    def _send(self, chat_id: str, msg_type: str, content: str) -> bool:
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )
        try:
            response = self._client.im.v1.message.create(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("发送飞书消息异常: %s", exc)
            return False
        if not response.success():
            logger.error(
                "发送飞书消息失败 code=%s msg=%s",
                getattr(response, "code", ""),
                getattr(response, "msg", ""),
            )
            return False
        return True

    @staticmethod
    def _build_card(answer: str, note: str = "") -> dict:
        """构建飞书卡片 2.0（schema 2.0）消息结构。"""
        return {
            "schema": "2.0",
            "header": {
                "title": {"tag": "plain_text", "content": "🔍 SRE 运维助手"},
                "template": "blue",
            },
            "body": {
                "elements": [
                    {"tag": "markdown", "content": answer},
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": note or "📖 回答基于 SRE 运维知识库",
                            }
                        ],
                    },
                ]
            },
        }


# 全局服务实例（由 init_services 初始化）
feishu_client: FeishuClient | None = None
conversation_store: ConversationStore | None = None
dify_client: DifyClient | None = None


def init_services() -> None:
    """初始化全局服务实例（在 main.py 启动时调用一次）。"""
    global feishu_client, conversation_store, dify_client
    domain = resolve_domain(config.FEISHU_DOMAIN)
    feishu_client = FeishuClient(config.FEISHU_APP_ID, config.FEISHU_APP_SECRET, domain)
    conversation_store = ConversationStore(config.CONVERSATION_TTL_SECONDS)
    dify_client = DifyClient(
        config.DIFY_API_BASE, config.DIFY_API_KEY, config.DIFY_TIMEOUT_SECONDS
    )


def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """接收消息 v2.0 事件回调（由 SDK 分发）。"""
    try:
        event = data.event
        message = event.message

        # 只处理文本消息
        if message.message_type != "text":
            return

        message_id = message.message_id or ""
        if not _mark_message_processed(message_id):
            return

        chat_id = message.chat_id or ""
        text = _extract_text(message)
        if not text:
            return

        sender = event.sender
        user_id = ""
        if sender is not None and sender.sender_id is not None:
            user_id = (
                sender.sender_id.open_id
                or sender.sender_id.union_id
                or sender.sender_id.user_id
                or ""
            )

        # 快速返回，实际处理放到后台线程，避免飞书 3 秒超时重推
        threading.Thread(
            target=_handle_message,
            args=(chat_id, user_id, text),
            daemon=True,
        ).start()
    except Exception:  # noqa: BLE001
        logger.exception("处理飞书事件异常")


def _handle_message(chat_id: str, user_id: str, text: str) -> None:
    """后台线程：处理一条用户消息（重置上下文 / 调用 Dify / 回复）。"""
    try:
        # 重置上下文指令
        if text in RESET_KEYWORDS:
            conversation_store.reset(user_id)
            feishu_client.send_text(chat_id, "✅ 已开启新对话，之前的上下文已清除。")
            return

        # 调用 Dify（带上已有的 conversation_id 以维持上下文）
        conv_id = conversation_store.get(user_id) or ""
        reply: DifyReply = dify_client.chat(text, conversation_id=conv_id, user=user_id)

        if reply.error:
            feishu_client.send_text(chat_id, f"⚠️ {reply.error}")
            return

        conversation_store.set(user_id, reply.conversation_id)

        if config.FEISHU_USE_CARD:
            ok = feishu_client.send_card(chat_id, reply.answer)
            if not ok:
                # 卡片发送失败时回退为纯文本
                feishu_client.send_text(chat_id, reply.answer)
        else:
            feishu_client.send_text(chat_id, reply.answer)
    except Exception:  # noqa: BLE001
        logger.exception("处理用户消息异常")
        try:
            feishu_client.send_text(chat_id, "⚠️ 服务出现异常，请稍后再试或联系 SRE 值班。")
        except Exception:  # noqa: BLE001
            logger.exception("发送兜底提示失败")


def build_event_handler():
    """构建并返回事件分发器（main.py 启动长连接时使用）。"""
    return (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
        .build()
    )
