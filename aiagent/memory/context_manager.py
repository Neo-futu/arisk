"""
aiagent/memory/context_manager.py — 短期記憶管理器

職責（Layer 2 — 短期記憶）：
  1. 維護對話滑動窗口（最多 MAX_TURNS 輪）
  2. Token 估算（按字符數估算，避免 tiktoken 依賴）
  3. 當 Token 超過閾值時，自動壓縮舊消息為摘要
  4. 保留最新 KEEP_RECENT 輪不壓縮（確保連貫性）

設計原則：
  - 不依賴任何 LLM 庫（由 runner.py 注入 summarize_fn）
  - 線程安全（asyncio 環境下使用）
  - 序列化友好（支持 JSON 序列化/反序列化）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# ── 配置常量 ─────────────────────────────────────────────────────
MAX_TURNS      = 40       # 最大保留輪數（user+assistant 各算一條）
TOKEN_THRESHOLD = 60_000  # 超過此估算 token 數時觸發壓縮
KEEP_RECENT    = 10       # 壓縮時保留最新 N 條不摘要
CHARS_PER_TOKEN = 2.5     # 中文字符/Token 估算比率（中文≈1.5字/token，含英文估算2.5）


class ContextManager:
    """
    對話上下文管理器。

    Usage:
        cm = ContextManager()
        cm.add("user", "請分析 BHMMF001 的 VaR")
        cm.add("assistant", "根據工具數據，VaR 為 ...")
        messages = cm.get_messages()   # 傳給 LLM 的 messages list
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id
        self._messages: list[dict] = []          # {role, content, ts}
        self._summary: str | None = None         # 壓縮後的歷史摘要
        self._total_compressed = 0               # 累計被壓縮的輪數

    # ── 添加消息 ─────────────────────────────────────────────────

    def add(self, role: str, content: str) -> None:
        """添加一條消息到上下文窗口。"""
        self._messages.append({
            "role":    role,
            "content": content,
            "ts":      datetime.now().isoformat(),
        })
        # 超過最大輪數時丟棄最舊消息（硬截斷，摘要由 maybe_compress 處理）
        if len(self._messages) > MAX_TURNS:
            self._messages = self._messages[-MAX_TURNS:]

    # ── 獲取 LLM 消息列表 ────────────────────────────────────────

    def get_messages(self) -> list[dict]:
        """
        返回可直接傳給 LLM 的 messages list。
        若存在歷史摘要，在最前面插入 system 消息注入摘要。
        """
        msgs = [{"role": m["role"], "content": m["content"]} for m in self._messages]
        if self._summary:
            summary_msg = {
                "role": "user",
                "content": f"【對話歷史摘要】以下為本次對話早期內容的摘要，供參考：\n{self._summary}",
            }
            msgs = [summary_msg] + msgs
        return msgs

    def get_raw(self) -> list[dict]:
        """返回含 ts 字段的原始消息列表（用於持久化）。"""
        return list(self._messages)

    # ── Token 估算 ───────────────────────────────────────────────

    def estimate_tokens(self) -> int:
        total_chars = sum(len(m["content"]) for m in self._messages)
        if self._summary:
            total_chars += len(self._summary)
        return int(total_chars / CHARS_PER_TOKEN)

    def is_near_limit(self) -> bool:
        return self.estimate_tokens() > TOKEN_THRESHOLD

    # ── 摘要壓縮 ─────────────────────────────────────────────────

    async def maybe_compress(
        self,
        summarize_fn: Callable[[list[dict]], Awaitable[str]],
    ) -> bool:
        """
        若上下文接近 Token 上限，壓縮舊消息。

        Args:
            summarize_fn: 異步函數，接受 messages list 返回摘要字符串。
                          由 runner.py 注入，避免循環依賴。

        Returns:
            True 表示執行了壓縮，False 表示無需壓縮。
        """
        if not self.is_near_limit():
            return False
        if len(self._messages) <= KEEP_RECENT:
            return False

        to_compress = self._messages[:-KEEP_RECENT]
        keep = self._messages[-KEEP_RECENT:]

        try:
            compress_msgs = [{"role": m["role"], "content": m["content"]} for m in to_compress]
            new_summary = await summarize_fn(compress_msgs)

            # 合并到現有摘要
            if self._summary:
                self._summary = f"{self._summary}\n\n{new_summary}"
            else:
                self._summary = new_summary

            self._messages = keep
            self._total_compressed += len(to_compress)
            logger.info(
                "[ContextManager] compressed %d messages, session=%s, total_compressed=%d",
                len(to_compress), self.session_id, self._total_compressed,
            )
            return True
        except Exception as exc:
            logger.warning("[ContextManager] summarization failed: %s", exc)
            return False

    # ── 持久化支持 ───────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id":        self.session_id,
            "messages":          self._messages,
            "summary":           self._summary,
            "total_compressed":  self._total_compressed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextManager":
        cm = cls(session_id=data.get("session_id"))
        cm._messages          = data.get("messages", [])
        cm._summary           = data.get("summary")
        cm._total_compressed  = data.get("total_compressed", 0)
        return cm

    def __repr__(self) -> str:
        return (
            f"ContextManager(session={self.session_id}, "
            f"msgs={len(self._messages)}, "
            f"tokens≈{self.estimate_tokens()}, "
            f"has_summary={self._summary is not None})"
        )
