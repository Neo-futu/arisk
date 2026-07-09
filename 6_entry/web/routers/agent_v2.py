"""
6_entry/web/routers/agent_v2.py — AI Agent V2 路由器

整合 aiagent/ 模塊，提供：
  POST /agent/v2/stream   — SSE 流式 + tool_use（主要端點）
  POST /agent/v2/chat     — 非流式 chat（兼容舊版）
  GET  /agent/v2/agents   — 可用 Agent 列表
  GET  /health            — 健康檢查

SSE 事件格式見 aiagent/README.md。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── aiagent 模塊路徑 ──────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aiagent.engine import sse_generator, AGENT_NAMES
from aiagent.engine.runner import run_agent, load_agent_prompt, SUPPORTED_MODELS, DEFAULT_MODEL
from aiagent.engine.tools import TOOLS

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Pydantic 模型 ─────────────────────────────────────────────────
class Message(BaseModel):
    role:    str    # "user" | "assistant"
    content: str


class StreamRequest(BaseModel):
    messages:   list[Message]
    agent:      str = "risk-analyst"
    context:    dict | None = None
    model:      str | None = None     # 模型 ID，None = 使用默認
    jwt_token:  str | None = None


class ChatRequest(BaseModel):
    message:   str
    agent:     str = "risk-analyst"
    context:   dict | None = None
    model:     str | None = None


# ── 端點 ──────────────────────────────────────────────────────────
@router.get("/agents", summary="查詢可用 Agent 列表")
def list_agents():
    return [{"id": k, "name": v} for k, v in AGENT_NAMES.items()]


@router.get("/models", summary="查詢支持的模型列表")
def list_models():
    """返回所有支持的模型，含 Provider 和默認標記。"""
    return [
        {
            "id":       model_id,
            "label":    info["label"],
            "provider": info["provider"],
            "default":  model_id == DEFAULT_MODEL,
        }
        for model_id, info in SUPPORTED_MODELS.items()
    ]


@router.post("/stream", summary="SSE 流式 Agent 對話（tool_use）")
async def stream_agent(req: StreamRequest):
    """
    主要端點：SSE 流式輸出，支持完整 tool_use 循環。

    前端使用 fetch + ReadableStream 接收（不用 EventSource）：
      const res = await fetch('/agent/v2/stream', {method:'POST', body: JSON.stringify(req)})
      const reader = res.body.getReader()
    """
    if req.agent not in AGENT_NAMES:
        raise HTTPException(400, f"未知 Agent：{req.agent}。可用：{list(AGENT_NAMES.keys())}")

    # 轉換 Pydantic Message 為 dict
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    return StreamingResponse(
        sse_generator(
            messages=messages,
            agent_name=req.agent,
            context=req.context,
            jwt_token=req.jwt_token,
            model=req.model,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",       # 禁止 Nginx 緩衝 SSE
        },
    )


@router.post("/chat", summary="非流式 chat（簡單問答 ≤30s）")
async def chat(req: ChatRequest):
    """
    簡單同步 chat，適合 ≤30s 的快速問答。
    返回完整文字結果（不流式）。
    """
    if req.agent not in AGENT_NAMES:
        raise HTTPException(400, f"未知 Agent：{req.agent}")

    messages = [{"role": "user", "content": req.message}]
    result_parts: list[str] = []
    tool_calls_used: list[dict] = []

    async for event in run_agent(
        messages=messages,
        agent_name=req.agent,
        context=req.context,
    ):
        if event["type"] == "text":
            result_parts.append(event["content"])
        elif event["type"] == "tool_call":
            tool_calls_used.append({"name": event["name"], "input": event["input"]})
        elif event["type"] == "error":
            raise HTTPException(500, event["message"])
        elif event["type"] == "done":
            break

    return {
        "reply":       "".join(result_parts),
        "agent":       req.agent,
        "tool_calls":  tool_calls_used,
        "model":       os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    }


@router.get("/tools", summary="查詢工具清單")
def list_tools():
    """返回 Agent 可調用的工具列表（供調試和文檔）。"""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in TOOLS
    ]
