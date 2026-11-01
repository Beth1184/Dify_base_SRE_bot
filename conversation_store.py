"""会话管理：维护「飞书用户 → Dify conversation_id」的映射。

用于在连续多轮对话中维持上下文（例如用户追问"如果是 Java 应用呢？"）。
当前实现为内存字典 + 超时过期，重启进程后丢失；如需生产级持久化，
可将本类替换为 Redis / SQLite 实现（对外接口保持不变）。
"""
from __future__ import annotations

import threading
import time


class ConversationStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, user_id: str) -> str | None:
        """获取用户的 conversation_id；不存在或已过期时返回 None。"""
        if not user_id:
            return None
        with self._lock:
            entry = self._data.get(user_id)
            if entry is None:
                return None
            if time.time() - entry["last_active"] > self._ttl:
                self._data.pop(user_id, None)
                return None
            entry["last_active"] = time.time()
            return entry["conversation_id"]

    def set(self, user_id: str, conversation_id: str) -> None:
        """记录（或刷新）用户的 conversation_id。"""
        if not user_id or not conversation_id:
            return
        with self._lock:
            self._data[user_id] = {
                "conversation_id": conversation_id,
                "last_active": time.time(),
            }

    def reset(self, user_id: str) -> None:
        """手动清除用户的会话上下文。"""
        with self._lock:
            self._data.pop(user_id, None)

    def clear_expired(self) -> int:
        """清理所有已过期会话，返回清理数量。"""
        now = time.time()
        with self._lock:
            expired = [u for u, e in self._data.items()
                       if now - e["last_active"] > self._ttl]
            for u in expired:
                self._data.pop(u, None)
        return len(expired)
