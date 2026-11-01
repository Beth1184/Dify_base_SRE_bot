"""配置管理：从项目根目录 .env 读取敏感信息与环境配置。

密钥等敏感信息一律放在 .env（已在 .gitignore 中忽略），
由使用者自行填充，本文件只负责读取与轻量校验。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# 优先加载项目根目录 .env（覆盖已存在的同名系统环境变量）
load_dotenv()


def _get_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # ---------- 飞书 ----------
    FEISHU_APP_ID: str = _get_str("FEISHU_APP_ID")
    FEISHU_APP_SECRET: str = _get_str("FEISHU_APP_SECRET")
    # 域名：feishu（国内飞书，默认）/ lark（国际版 Lark）
    FEISHU_DOMAIN: str = _get_str("FEISHU_DOMAIN", "feishu")

    # ---------- Dify ----------
    DIFY_API_BASE: str = _get_str("DIFY_API_BASE", "https://api.dify.ai/v1")
    DIFY_API_KEY: str = _get_str("DIFY_API_KEY")
    DIFY_TIMEOUT_SECONDS: int = _get_int("DIFY_TIMEOUT_SECONDS", 60)

    # ---------- 会话 ----------
    CONVERSATION_TTL_SECONDS: int = _get_int("CONVERSATION_TTL_SECONDS", 1800)

    # ---------- 消息 ----------
    FEISHU_USE_CARD: bool = _get_bool("FEISHU_USE_CARD", True)

    def validate(self) -> list[str]:
        """返回缺失的必要配置项；为空表示配置完整。"""
        missing: list[str] = []
        if not self.FEISHU_APP_ID:
            missing.append("FEISHU_APP_ID")
        if not self.FEISHU_APP_SECRET:
            missing.append("FEISHU_APP_SECRET")
        if not self.DIFY_API_KEY:
            missing.append("DIFY_API_KEY")
        return missing


config = Config()
