"""
用戶專屬 AI Agent 配置 API。

每個用戶擁有唯一一份 Agent 配置，控制：
  - 默認使用的模型和 Agent 角色
  - 個人自定義指令（注入每次對話的 system prompt）
  - 工具啟用清單、記憶開關
  - Agent 名稱（用戶為自己的助理命名）

端點：
  GET  /api/v1/agent-config/me        — 查詢當前用戶的 Agent 配置（不存在則返回默認值）
  PUT  /api/v1/agent-config/me        — 更新（upsert）當前用戶的 Agent 配置
  DELETE /api/v1/agent-config/me/reset — 重置為系統默認配置
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import UserAgentConfig, UserAgentConfigPublic, UserAgentConfigUpdate

router = APIRouter()

_DEFAULTS = dict(
    agent_name=None,
    default_agent_id="general",
    default_model_id="claude-sonnet-4-6",
    custom_instructions=None,
    tools_enabled="[]",
    memory_enabled=True,
    rag_enabled=True,
    max_context_turns=40,
)


@router.get("/me", response_model=UserAgentConfigPublic)
def get_my_agent_config(session: SessionDep, current_user: CurrentUser) -> Any:
    """查詢當前用戶的 Agent 配置。不存在時自動創建默認配置。"""
    cfg = session.get(UserAgentConfig, current_user.id)
    if not cfg:
        cfg = _create_default(session, current_user.id)
    return cfg


@router.put("/me", response_model=UserAgentConfigPublic)
def update_my_agent_config(
    body:         UserAgentConfigUpdate,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    """更新當前用戶的 Agent 配置（upsert：不存在則自動創建）。"""
    cfg = session.get(UserAgentConfig, current_user.id)
    if not cfg:
        cfg = _create_default(session, current_user.id)

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(cfg, field, value)
    cfg.updated_at = datetime.now(UTC)

    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


@router.delete("/me/reset", response_model=UserAgentConfigPublic)
def reset_my_agent_config(session: SessionDep, current_user: CurrentUser) -> Any:
    """重置當前用戶的 Agent 配置為系統默認值。"""
    cfg = session.get(UserAgentConfig, current_user.id)
    if cfg:
        for field, value in _DEFAULTS.items():
            setattr(cfg, field, value)
        cfg.updated_at = datetime.now(UTC)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    else:
        cfg = _create_default(session, current_user.id)
    return cfg


def _create_default(session, user_id: uuid.UUID) -> UserAgentConfig:
    now = datetime.now(UTC)
    cfg = UserAgentConfig(
        user_id=user_id,
        created_at=now,
        updated_at=now,
        **_DEFAULTS,
    )
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg
