"""Agent 審核阻塞點（Checkpoint）：讓 agent 在關鍵操作前暫停等待人工批准。

使用方式（在 agent 或 processing 代碼中）：

    async with ReviewCheckpoint(
        db, redis,
        category="COMPLIANCE_BREACH",
        title="WAM 超限：60.3 天 > 60 天上限",
        summary="...",
        triggered_by="risk-agent",
        fund_id="BHMMF",
        payload={"breach_flags": {"WAM_BREACH": True}},
    ) as approved:
        if approved:
            # 執行被保護的寫入操作
            await do_write_to_db(...)
        else:
            # 審核被拒絕，記錄並中止
            logger.warning("Action blocked by review: rejected")

或使用裝飾器（適合 Processing API 的路由函數）：

    @requires_review(category="DATA_WRITE", title="批量持倉更新")
    async def update_positions(fund_id: str, ...):
        ...
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .review_manager import create_review_request

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0       # 輪詢間隔（秒）
MAX_WAIT_SECONDS = 3600   # 最長等待 1 小時
REDIS_CHANNEL_PREFIX = "fsi:review:decision:"


@asynccontextmanager
async def ReviewCheckpoint(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    category: str,
    title: str,
    summary: str,
    triggered_by: str,
    payload: dict,
    fund_id: str | None = None,
    as_of_date=None,
    task_id: str | None = None,
    artefact_path: str | None = None,
    artefact_url: str | None = None,
    timeout_seconds: int = MAX_WAIT_SECONDS,
) -> AsyncIterator[bool]:
    """
    非同步上下文管理器。

    進入時：創建審核請求，登記 agent_checkpoint，掛起等待。
    退出時：根據審核結果讓調用方決定繼續或中止。
    """
    checkpoint_id = str(uuid.uuid4())

    # 1. 創建審核請求
    review_id = await create_review_request(
        db,
        category=category,
        title=title,
        summary=summary,
        triggered_by=triggered_by,
        payload=payload,
        fund_id=fund_id,
        as_of_date=as_of_date,
        task_id=task_id,
        artefact_path=artefact_path,
        artefact_url=artefact_url,
    )

    # 2. 登記 checkpoint（記錄 agent 在此暫停）
    await db.execute(
        text("""
            INSERT INTO fsi.agent_checkpoints
                (checkpoint_id, review_id, agent_name, task_id, checkpoint_name, blocked_action, context_snapshot)
            VALUES (:cid, :rid, :agent, :tid, :name, :action, :ctx)
        """),
        {
            "cid": checkpoint_id,
            "rid": review_id,
            "agent": triggered_by,
            "tid": task_id or "",
            "name": title,
            "action": summary,
            "ctx": json.dumps({"fund_id": fund_id, "payload_keys": list(payload.keys())}),
        },
    )
    await db.commit()

    logger.info(
        "Checkpoint BLOCKED: %s → review_id=%s  (category=%s, fund=%s)",
        checkpoint_id, review_id, category, fund_id,
    )

    # 3. 訂閱 Redis 頻道等待決策通知
    channel = f"{REDIS_CHANNEL_PREFIX}{review_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    approved = False
    try:
        elapsed = 0.0
        async for message in pubsub.listen():
            if message["type"] == "message":
                decision = message["data"]
                if isinstance(decision, bytes):
                    decision = decision.decode()
                approved = (decision == "APPROVED")
                break
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            if elapsed >= timeout_seconds:
                logger.warning("Checkpoint timed out after %ds: review_id=%s", timeout_seconds, review_id)
                break
    finally:
        await pubsub.unsubscribe(channel)

    yield approved


def requires_review(
    category: str,
    title: str,
    summary: str = "",
    fund_id_param: str = "fund_id",
    timeout_seconds: int = MAX_WAIT_SECONDS,
):
    """
    裝飾器版本：適合 FastAPI 路由或普通 async 函數。

    使用方式：
        @requires_review(category="DATA_WRITE", title="批量持倉更新")
        async def load_positions(fund_id: str, db: AsyncSession, redis: aioredis.Redis, ...):
            ...

    函數必須接受 db 和 redis 參數。
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db: AsyncSession = kwargs.get("db")
            redis: aioredis.Redis = kwargs.get("redis")
            fund_id = kwargs.get(fund_id_param)

            if db is None or redis is None:
                logger.warning("requires_review: db or redis not in kwargs, skipping checkpoint")
                return await func(*args, **kwargs)

            import inspect
            caller = f"{func.__module__}.{func.__qualname__}"

            async with ReviewCheckpoint(
                db, redis,
                category=category,
                title=title,
                summary=summary or f"函數 {caller} 需要人工批准",
                triggered_by=caller,
                payload={"args": str(kwargs)[:500]},
                fund_id=fund_id,
                timeout_seconds=timeout_seconds,
            ) as approved:
                if approved:
                    return await func(*args, **kwargs)
                else:
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=403,
                        detail=f"操作被人工審核拒絕：{title}",
                    )
        return wrapper
    return decorator


async def notify_decision(redis: aioredis.Redis, review_id: str, action: str) -> None:
    """
    由 review API 在批准/拒絕後調用，通過 Redis pub/sub 通知等待的 checkpoint。
    action: "APPROVED" | "REJECTED"
    """
    channel = f"{REDIS_CHANNEL_PREFIX}{review_id}"
    await redis.publish(channel, action)
    logger.info("Decision published to channel %s: %s", channel, action)
