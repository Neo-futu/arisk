"""
用戶個人工具 CRUD API。

每個業務用戶可以為自己的 Chat Agent 定義個人化工具：
  - 添加自定義 API 端點作為工具
  - Chat Agent 在對話時自動加載並調用

場景示例：
  - 用戶「張三」添加工具：查詢自己公司內部系統的持倉數據
  - 用戶「李四」添加工具：調用彭博 API 查詢信用評級
  - 不需要開發者介入，用戶自助配置

端點：
  GET    /api/v1/custom-tools/          查詢我的工具列表
  POST   /api/v1/custom-tools/          添加新工具
  PUT    /api/v1/custom-tools/{id}      更新工具
  DELETE /api/v1/custom-tools/{id}      刪除工具
  PUT    /api/v1/custom-tools/{id}/toggle 啟用/停用
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    UserCustomTool,
    UserCustomToolCreate,
    UserCustomToolPublic,
    UserCustomToolUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[UserCustomToolPublic])
def list_my_tools(session: SessionDep, current_user: CurrentUser) -> Any:
    """查詢當前用戶的所有個人工具。"""
    tools = session.exec(
        select(UserCustomTool)
        .where(UserCustomTool.user_id == current_user.id)
        .order_by(UserCustomTool.created_at)
    ).all()
    return tools


@router.post("/", response_model=UserCustomToolPublic)
def create_tool(
    body:         UserCustomToolCreate,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    """添加新個人工具。"""
    # 工具名在同一用戶下必須唯一
    existing = session.exec(
        select(UserCustomTool).where(
            UserCustomTool.user_id   == current_user.id,
            UserCustomTool.tool_name == body.tool_name,
        )
    ).first()
    if existing:
        raise HTTPException(409, f"工具名已存在：{body.tool_name}")

    now  = datetime.now(UTC)
    tool = UserCustomTool(
        user_id=current_user.id,
        created_at=now,
        updated_at=now,
        **body.model_dump(),
    )
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return tool


@router.put("/{tool_id}", response_model=UserCustomToolPublic)
def update_tool(
    tool_id:      uuid.UUID,
    body:         UserCustomToolUpdate,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    """更新個人工具配置。"""
    tool = _get_own_tool(session, tool_id, current_user.id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tool, field, value)
    tool.updated_at = datetime.now(UTC)
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return tool


@router.delete("/{tool_id}")
def delete_tool(
    tool_id:      uuid.UUID,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    """刪除個人工具。"""
    tool = _get_own_tool(session, tool_id, current_user.id)
    session.delete(tool)
    session.commit()
    return {"deleted": str(tool_id)}


@router.put("/{tool_id}/toggle", response_model=UserCustomToolPublic)
def toggle_tool(
    tool_id:      uuid.UUID,
    session:      SessionDep,
    current_user: CurrentUser,
) -> Any:
    """切換工具啟用/停用狀態。"""
    tool = _get_own_tool(session, tool_id, current_user.id)
    tool.enabled    = not tool.enabled
    tool.updated_at = datetime.now(UTC)
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return tool


def _get_own_tool(session, tool_id: uuid.UUID, user_id: uuid.UUID) -> UserCustomTool:
    tool = session.get(UserCustomTool, tool_id)
    if not tool or tool.user_id != user_id:
        raise HTTPException(404, "工具不存在")
    return tool
