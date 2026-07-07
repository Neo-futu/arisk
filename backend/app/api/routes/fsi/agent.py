"""FSI Agent / Chat 代理路由。

對外統一掛載在 /api/v1/fsi/agent/*，由 backend 承擔 JWT 認證，
內部再轉發到 6_entry 服務，避免前端直接調用多個入口。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, EntryClient

router = APIRouter()


class AgentTaskRequest(BaseModel):
    task: str
    fund_id: str | None = None
    date: str | None = None
    mode: str = "agent"


class VarSkillRequest(BaseModel):
    fund_id: str
    as_of_date: str
    confidence: float = 0.99
    horizon_days: int = 1
    simulations: int = 10000


async def _proxy_post(client: EntryClient, path: str, payload: dict[str, Any]) -> Any:
    resp = await client.post(path, json=payload)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def _proxy_get(client: EntryClient, path: str) -> Any:
    resp = await client.get(path)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/chat", summary="與 Agent 同步對話")
async def chat_with_agent(
    request: AgentTaskRequest,
    _user: CurrentUser,
    client: EntryClient,
) -> Any:
    return await _proxy_post(client, "/agent/chat", request.model_dump())


@router.post("/run", summary="提交 Agent 異步任務")
async def run_agent_task(
    request: AgentTaskRequest,
    _user: CurrentUser,
    client: EntryClient,
) -> Any:
    return await _proxy_post(client, "/agent/run", request.model_dump())


@router.get("/status/{task_id}", summary="查詢 Agent 任務狀態")
async def get_agent_task_status(
    task_id: str,
    _user: CurrentUser,
    client: EntryClient,
) -> Any:
    return await _proxy_get(client, f"/agent/status/{task_id}")


@router.post("/skills/var-analysis", summary="Agent VaR skill 代理")
async def run_agent_var_skill(
    request: VarSkillRequest,
    _user: CurrentUser,
    client: EntryClient,
) -> Any:
    return await _proxy_post(client, "/agent/skills/var-analysis", request.model_dump())