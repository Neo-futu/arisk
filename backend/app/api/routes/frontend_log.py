"""前端日誌收集端點。

接收瀏覽器端上報的日誌（用戶行為 / 操作 / 審計 / 錯誤），
持久化到 chatdb.frontend_log 表，供後台審計和排障使用。
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models import IAM_SCHEMA, CHAT_SCHEMA

router = APIRouter()


# ── Pydantic ──────────────────────────────────────────────────────

class LogEntryIn(BaseModel):
    log_type: str   # user_action | operation | audit | error
    level:    str = "info"
    module:   str
    action:   str
    detail:   dict | None = None
    url:      str | None = None


class LogBatch(BaseModel):
    entries: list[LogEntryIn]


# ── 寫入 ──────────────────────────────────────────────────────────

@router.post("/batch", summary="批量上報前端日誌")
def save_log_batch(
    body:         LogBatch,
    request:      Request,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    user_agent = request.headers.get("user-agent", "")[:500]
    now = datetime.now(UTC)

    from sqlalchemy import text
    rows = [
        {
            "id":         str(uuid.uuid4()),
            "user_id":    str(current_user.id),
            "log_type":   e.log_type[:30],
            "level":      e.level[:10],
            "module":     e.module[:100],
            "action":     e.action[:200],
            "detail":     json.dumps(e.detail, ensure_ascii=False) if e.detail else None,
            "user_agent": user_agent,
            "url":        (e.url or "")[:500],
            "created_at": now,
        }
        for e in body.entries
    ]

    if rows:
        session.exec(  # type: ignore[call-overload]
            text(f"""
                INSERT INTO {CHAT_SCHEMA}.frontend_log
                    (id, user_id, log_type, level, module, action, detail, user_agent, url, created_at)
                VALUES
                    (:id, :user_id, :log_type, :level, :module, :action, :detail, :user_agent, :url, :created_at)
            """),
            rows,
        )
        session.commit()

    return {"saved": len(rows)}


# ── 查詢（僅超管） ─────────────────────────────────────────────────

@router.get("/", summary="查詢前端日誌（超管）")
def list_logs(
    session:      SessionDep,
    current_user: CurrentUser,
    log_type: str | None = None,
    level:    str | None = None,
    limit:    int = 200,
) -> Any:
    if not current_user.is_superuser:
        from fastapi import HTTPException
        raise HTTPException(403, "需要超管權限")

    from sqlalchemy import text
    where = ["1=1"]
    params: dict = {"limit": limit}
    if log_type: where.append("log_type = :log_type"); params["log_type"] = log_type
    if level:    where.append("level = :level");       params["level"]    = level

    rows = session.exec(  # type: ignore[call-overload]
        text(f"""
            SELECT id, user_id, log_type, level, module, action, detail, url, created_at
            FROM {CHAT_SCHEMA}.frontend_log
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        params,
    ).mappings().fetchall()

    return [dict(r) for r in rows]
