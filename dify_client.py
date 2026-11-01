"""Dify Chat API 调用封装。

使用 Dify 的 /chat-messages 接口（blocking 模式）：
- 发送用户问题，返回机器人的回答与 conversation_id
- conversation_id 用于维持多轮上下文
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class DifyReply:
    answer: str = ""
    conversation_id: str = ""
    error: str = ""


class DifyClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, query: str, conversation_id: str = "", user: str = "") -> DifyReply:
        """发送一次对话请求，返回回答与新的 conversation_id。"""
        url = f"{self.base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": conversation_id or "",
            "user": user or "feishu_user",
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout:
            logger.warning("Dify API 请求超时")
            return DifyReply(error="处理超时，请稍后再试")
        except requests.exceptions.RequestException as exc:
            logger.error("Dify API 请求异常: %s", exc)
            return DifyReply(error="暂时无法连接知识库服务，请稍后再试")

        if resp.status_code != 200:
            logger.error("Dify API 返回异常状态码 %s: %s", resp.status_code, resp.text[:500])
            return DifyReply(error="知识库服务返回异常，请稍后再试")

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error("Dify API 返回内容解析失败: %s", exc)
            return DifyReply(error="知识库返回内容解析失败")

        answer = data.get("answer") or ""
        conv_id = data.get("conversation_id") or ""
        if not answer:
            return DifyReply(conversation_id=conv_id, error="未找到相关信息")

        return DifyReply(answer=answer, conversation_id=conv_id)
