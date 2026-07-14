"""platform_agent Redis task state machine."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KEY_PREFIX = "arisk:platform_task"
TTL_TASK = 86_400
TTL_RESULT = 604_800


class PlatformTaskStatus(str, Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlatformTaskState:
    """Redis-backed task tracker for platform workflows."""

    def __init__(self, task_id: str, _redis=None) -> None:
        self.task_id = task_id
        self._redis = _redis
        self._key = f"{KEY_PREFIX}:{task_id}"
        self._log_key = f"{KEY_PREFIX}:{task_id}:log"
        self._res_key = f"{KEY_PREFIX}:{task_id}:result"

    @classmethod
    async def create(
        cls,
        agent_id: str,
        query: str,
        model_id: str = "",
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> "PlatformTaskState":
        task_id = str(uuid.uuid4())
        ts = cls(task_id)
        try:
            ts._redis = await _get_redis()
            now = datetime.now().isoformat()
            await ts._redis.hset(ts._key, mapping={
                "task_id": task_id,
                "status": PlatformTaskStatus.QUEUED.value,
                "agent_id": agent_id,
                "model_id": model_id,
                "query": query[:500],
                "session_id": session_id or "",
                "user_id": user_id or "",
                "created_at": now,
                "updated_at": now,
                "error": "",
            })
            await ts._redis.expire(ts._key, TTL_TASK)
        except Exception as exc:
            logger.warning("[PlatformTaskState] Redis not available: %s", exc)
        return ts

    async def transition(self, status: PlatformTaskStatus) -> None:
        if not self._redis:
            return
        try:
            await self._redis.hset(self._key, mapping={
                "status": status.value,
                "updated_at": datetime.now().isoformat(),
            })
        except Exception as exc:
            logger.warning("[PlatformTaskState] transition failed: %s", exc)

    async def log(self, message: str) -> None:
        if not self._redis:
            return
        try:
            entry = json.dumps({"ts": datetime.now().isoformat(), "msg": message}, ensure_ascii=False)
            await self._redis.rpush(self._log_key, entry)
            await self._redis.expire(self._log_key, TTL_TASK)
        except Exception:
            pass

    async def complete(self, result: Any) -> None:
        if not self._redis:
            return
        try:
            payload = json.dumps(result, ensure_ascii=False, default=str)
            await self._redis.setex(self._res_key, TTL_RESULT, payload)
            await self.transition(PlatformTaskStatus.DONE)
        except Exception as exc:
            logger.warning("[PlatformTaskState] complete failed: %s", exc)

    async def fail(self, error: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.hset(self._key, mapping={
                "status": PlatformTaskStatus.FAILED.value,
                "error": error[:500],
                "updated_at": datetime.now().isoformat(),
            })
        except Exception as exc:
            logger.warning("[PlatformTaskState] fail failed: %s", exc)


_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client
