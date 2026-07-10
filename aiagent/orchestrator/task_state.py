"""
aiagent/orchestrator/task_state.py — Layer 4: Redis 任務狀態機

任務生命週期（State Machine）：

  QUEUED → PLANNING → EXECUTING → REFLECTING → DONE
                                              ↘ FAILED

狀態說明：
  QUEUED     — 任務已提交，等待 worker 處理
  PLANNING   — Planner 正在生成執行計劃（Layer 1）
  EXECUTING  — Agent ReAct 循環執行中（Layer 1+3）
  REFLECTING — Reflector 正在評估輸出（Layer 1）
  DONE       — 成功完成
  FAILED     — 執行失敗（含錯誤信息）
  CANCELLED  — 用戶取消

Redis Key 規則（帶 TTL，避免殘留）：
  arisk:task:{task_id}        — 任務狀態 Hash（TTL: 24h）
  arisk:task:{task_id}:log    — 任務日誌 List（TTL: 24h）
  arisk:task:{task_id}:result — 最終結果 String（TTL: 7d）
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KEY_PREFIX   = "arisk:task"
TTL_TASK     = 86_400      # 24 小時
TTL_RESULT   = 604_800     # 7 天


class TaskStatus(str, Enum):
    QUEUED     = "queued"
    PLANNING   = "planning"
    EXECUTING  = "executing"
    REFLECTING = "reflecting"
    DONE       = "done"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


class TaskState:
    """
    Redis 任務狀態管理器。

    Usage:
        ts = await TaskState.create(agent_id="risk-analyst", query="...")
        await ts.transition(TaskStatus.PLANNING)
        await ts.log("開始生成執行計劃")
        await ts.transition(TaskStatus.EXECUTING)
        await ts.complete(result={"summary": "..."})
    """

    def __init__(self, task_id: str, _redis=None) -> None:
        self.task_id   = task_id
        self._redis    = _redis
        self._key      = f"{KEY_PREFIX}:{task_id}"
        self._log_key  = f"{KEY_PREFIX}:{task_id}:log"
        self._res_key  = f"{KEY_PREFIX}:{task_id}:result"

    # ── 工廠方法 ─────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        agent_id:   str,
        query:      str,
        model_id:   str = "",
        session_id: str | None = None,
        user_id:    str | None = None,
    ) -> "TaskState":
        """創建新任務，寫入 Redis，返回 TaskState 實例。"""
        task_id = str(uuid.uuid4())
        ts = cls(task_id)
        try:
            ts._redis = await _get_redis()
            now = datetime.now().isoformat()
            await ts._redis.hset(ts._key, mapping={
                "task_id":   task_id,
                "status":    TaskStatus.QUEUED,
                "agent_id":  agent_id,
                "model_id":  model_id,
                "query":     query[:500],
                "session_id": session_id or "",
                "user_id":   user_id or "",
                "created_at": now,
                "updated_at": now,
                "error":     "",
            })
            await ts._redis.expire(ts._key, TTL_TASK)
        except Exception as exc:
            logger.warning("[TaskState] Redis not available: %s", exc)
        return ts

    @classmethod
    async def load(cls, task_id: str) -> "TaskState | None":
        """從 Redis 加載任務狀態。"""
        ts = cls(task_id)
        try:
            ts._redis = await _get_redis()
            exists = await ts._redis.exists(ts._key)
            if not exists:
                return None
            return ts
        except Exception:
            return None

    # ── 狀態轉換 ─────────────────────────────────────────────────

    async def transition(self, status: TaskStatus) -> None:
        """轉換到新狀態，更新 updated_at。"""
        if not self._redis:
            return
        try:
            await self._redis.hset(self._key, mapping={
                "status":     status.value,
                "updated_at": datetime.now().isoformat(),
            })
        except Exception as exc:
            logger.warning("[TaskState] transition failed: %s", exc)

    async def complete(self, result: Any) -> None:
        """標記任務完成並保存結果。"""
        if not self._redis:
            return
        try:
            result_json = json.dumps(result, ensure_ascii=False, default=str)
            await self._redis.setex(self._res_key, TTL_RESULT, result_json)
            await self.transition(TaskStatus.DONE)
        except Exception as exc:
            logger.warning("[TaskState] complete failed: %s", exc)

    async def fail(self, error: str) -> None:
        """標記任務失敗。"""
        if not self._redis:
            return
        try:
            await self._redis.hset(self._key, mapping={
                "status":     TaskStatus.FAILED.value,
                "error":      error[:500],
                "updated_at": datetime.now().isoformat(),
            })
        except Exception as exc:
            logger.warning("[TaskState] fail failed: %s", exc)

    # ── 日誌 ─────────────────────────────────────────────────────

    async def log(self, message: str) -> None:
        """追加日誌條目（List RPUSH）。"""
        if not self._redis:
            return
        try:
            entry = json.dumps({"ts": datetime.now().isoformat(), "msg": message}, ensure_ascii=False)
            await self._redis.rpush(self._log_key, entry)
            await self._redis.expire(self._log_key, TTL_TASK)
        except Exception:
            pass

    # ── 讀取 ─────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """返回任務狀態 dict。"""
        if not self._redis:
            return {"task_id": self.task_id, "status": "unknown"}
        try:
            data = await self._redis.hgetall(self._key)
            return {k.decode(): v.decode() for k, v in data.items()} if data else {}
        except Exception:
            return {}

    async def get_result(self) -> Any:
        """返回任務結果（JSON parse）。"""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(self._res_key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def get_logs(self, limit: int = 50) -> list[dict]:
        """返回最新 N 條日誌。"""
        if not self._redis:
            return []
        try:
            raw_list = await self._redis.lrange(self._log_key, -limit, -1)
            return [json.loads(r) for r in raw_list]
        except Exception:
            return []


# ── Redis 連接 ────────────────────────────────────────────────────

_redis_client = None

async def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client
