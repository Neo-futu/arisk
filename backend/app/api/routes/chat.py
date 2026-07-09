"""Chat Session / Message CRUD — 聊天歷史持久化。

路由：/api/v1/chat/*
所有端點需要 JWT 認證，數據隔離到當前用戶。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ChatMessage,
    ChatMessageBatch,
    ChatMessagePublic,
    ChatSession,
    ChatSessionCreate,
    ChatSessionPublic,
    ChatSessionUpdate,
)

router = APIRouter()


# ── Sessions ──────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[ChatSessionPublic])
def list_sessions(session: SessionDep, current_user: CurrentUser) -> Any:
    """返回當前用戶所有會話，按最近更新倒序。"""
    rows = session.exec(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())  # type: ignore[arg-type]
    ).all()
    return rows


@router.post("/sessions", response_model=ChatSessionPublic)
def create_session(
    body: ChatSessionCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """新建聊天會話。"""
    now = datetime.now(UTC)
    chat_session = ChatSession(
        user_id=current_user.id,
        title=body.title or "新對話",
        agent_id=body.agent_id,
        model_id=body.model_id,
        created_at=now,
        updated_at=now,
    )
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session


@router.patch("/sessions/{session_id}", response_model=ChatSessionPublic)
def update_session(
    session_id: uuid.UUID,
    body: ChatSessionUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """更新會話標題 / Agent / 模型，並刷新 updated_at。"""
    chat_session = _get_own_session(session, session_id, current_user.id)
    if body.title    is not None: chat_session.title    = body.title
    if body.agent_id is not None: chat_session.agent_id = body.agent_id
    if body.model_id is not None: chat_session.model_id = body.model_id
    chat_session.updated_at = datetime.now(UTC)
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """刪除會話及其所有消息（CASCADE）。"""
    chat_session = _get_own_session(session, session_id, current_user.id)
    # 先刪消息（psycopg sync 不保證 CASCADE 在 SQLModel 層生效）
    msgs = session.exec(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    ).all()
    for m in msgs:
        session.delete(m)
    session.delete(chat_session)
    session.commit()
    return {"ok": True}


# ── Messages ──────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessagePublic])
def get_messages(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """返回指定會話的所有消息，按時間升序。"""
    _get_own_session(session, session_id, current_user.id)
    msgs = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())  # type: ignore[arg-type]
    ).all()
    return msgs


@router.post("/sessions/{session_id}/messages", response_model=list[ChatMessagePublic])
def save_messages(
    session_id: uuid.UUID,
    body: ChatMessageBatch,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """批量追加消息並更新會話 updated_at。"""
    chat_session = _get_own_session(session, session_id, current_user.id)
    import json
    now = datetime.now(UTC)
    saved = []
    for m in body.messages:
        tool_calls = m.get("tool_calls", [])
        msg = ChatMessage(
            session_id=session_id,
            role=m["role"],
            content=m.get("content", ""),
            tool_calls=json.dumps(tool_calls, ensure_ascii=False) if isinstance(tool_calls, list) else tool_calls,
            created_at=now,
        )
        session.add(msg)
        saved.append(msg)
    chat_session.updated_at = now
    session.add(chat_session)
    session.commit()
    for msg in saved:
        session.refresh(msg)
    return saved


# ── Helper ────────────────────────────────────────────────────────

def _get_own_session(session: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession:
    chat_session = session.get(ChatSession, session_id)
    if not chat_session or chat_session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return chat_session
