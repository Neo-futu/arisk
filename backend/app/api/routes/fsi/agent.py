"""FSI Agent / Chat 代理路由。

對外統一掛載在 /api/v1/fsi/agent/*，由 backend 承擔 JWT 認證，
內部再轉發到 6_entry 服務，避免前端直接調用多個入口。
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, EntryClient

router = APIRouter()


class AgentTaskRequest(BaseModel):
    task: str
    fund_id: str | None = None
    date: str | None = None
    mode: str = "agent"


class Message(BaseModel):
    role:    str
    content: str


class StreamRequest(BaseModel):
    messages: list[Message]
    agent:    str = "risk-analyst"
    context:  dict | None = None
    model:    str | None = None


class ChatV2Request(BaseModel):
    message: str
    agent:   str = "risk-analyst"
    context: dict | None = None


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


# ── Agent V2 — SSE 流式 + tool_use ─────────────────────────────────

_STATIC_AGENTS = [
    {"id": "general",            "name": "通用助理"},
    {"id": "risk-analyst",       "name": "ARISK 風控分析師"},
    {"id": "compliance-officer", "name": "SFC 合規審查員"},
    {"id": "fund-reporter",      "name": "基金報表助理"},
    {"id": "market-researcher",  "name": "市場研究員"},
    {"id": "gl-reconciler",      "name": "基金 GL 對賬員"},
    {"id": "kyc-screener",       "name": "KYC 合規篩查員"},
    {"id": "statement-auditor",  "name": "NAV 報表審計員"},
    {"id": "valuation-reviewer", "name": "組合估值審查員"},
    {"id": "month-end-closer",   "name": "月末結賬助手"},
]


@router.get("/v2/agents", summary="可用 Agent 列表")
async def list_agents_v2(_user: CurrentUser) -> Any:
    return _STATIC_AGENTS


_STATIC_MODELS = [
    # Anthropic Claude
    {"id": "claude-sonnet-4-6",           "label": "Claude Sonnet 4.6（推薦）",           "provider": "anthropic",   "default": True},
    {"id": "claude-opus-4-5",             "label": "Claude Opus 4.5（最強）",             "provider": "anthropic",   "default": False},
    {"id": "claude-haiku-4-5-20251001",   "label": "Claude Haiku 4.5（最快）",            "provider": "anthropic",   "default": False},
    # Google Gemini
    {"id": "gemini-2.0-flash",            "label": "Gemini 2.0 Flash",                    "provider": "gemini",      "default": False},
    {"id": "gemini-1.5-pro",              "label": "Gemini 1.5 Pro",                      "provider": "gemini",      "default": False},
    # OpenAI
    {"id": "gpt-4o",                      "label": "GPT-4o",                              "provider": "openai",      "default": False},
    {"id": "gpt-4o-mini",                 "label": "GPT-4o Mini",                         "provider": "openai",      "default": False},
    # Kimi
    {"id": "moonshot-v1-32k",             "label": "Kimi moonshot-v1-32k（推薦）",         "provider": "moonshot",    "default": False},
    {"id": "moonshot-v1-128k",            "label": "Kimi moonshot-v1-128k（長文）",        "provider": "moonshot",    "default": False},
    # DeepSeek
    {"id": "deepseek-chat",               "label": "DeepSeek Chat V3（推薦）",             "provider": "deepseek",    "default": False},
    {"id": "deepseek-reasoner",           "label": "DeepSeek R1（推理增強）",              "provider": "deepseek",    "default": False},
    # xAI Grok via OpenRouter
    {"id": "x-ai/grok-4.20",             "label": "xAI Grok 4.20（最新旗艦）",            "provider": "openrouter",  "default": False},
    {"id": "x-ai/grok-4.3",              "label": "xAI Grok 4.3",                        "provider": "openrouter",  "default": False},
]


@router.get("/v2/models", summary="支持的模型列表")
async def list_models_v2(_user: CurrentUser) -> Any:
    return _STATIC_MODELS


@router.get("/v2/tools", summary="可用工具清單")
async def list_tools_v2(_user: CurrentUser, client: EntryClient) -> Any:
    return await _proxy_get(client, "/agent/v2/tools")


@router.post("/v2/chat", summary="Agent V2 非流式 chat")
async def chat_v2(
    request: ChatV2Request,
    _user: CurrentUser,
    client: EntryClient,
) -> Any:
    return await _proxy_post(client, "/agent/v2/chat", request.model_dump())


@router.post("/v2/stream", summary="Agent V2 SSE 流式對話（tool_use）")
async def stream_v2(
    request: StreamRequest,
    _user: CurrentUser,
    client: EntryClient,
):
    """
    SSE 流式代理：把 6_entry:8010/agent/v2/stream 的 SSE 流直接透傳給前端。
    前端用 fetch + ReadableStream 接收。
    """
    # 注入 JWT token 到請求，讓工具層可選擇 via_backend 調用
    payload = request.model_dump()
    payload["jwt_token"] = str(_user.id) if getattr(_user, "id", None) is not None else None

    # httpx 流式代理：透傳 SSE bytes
    async def _stream_proxy():
        try:
            async with client.stream("POST", "/agent/v2/stream", json=payload) as resp:
                if resp.status_code != 200:
                    yield f"data: {{\"type\":\"error\",\"message\":\"6_entry error {resp.status_code}\"}}\n\n"
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError:
            yield "data: {\"type\":\"error\",\"message\":\"Agent service not running (port 8010). Start with: python scripts/dev.py\"}\n\n"

    return StreamingResponse(
        _stream_proxy(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )