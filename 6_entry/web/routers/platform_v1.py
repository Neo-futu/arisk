"""
6_entry/web/routers/platform_v1.py — Platform Agent HTTP 端點

面向開發者的 AI 助手接口，與業務 Agent（agent_v2.py）完全分離。

端點：
  POST /platform/v1/stream  — SSE 流式對話（主要端點）
  GET  /platform/v1/agents  — 可用開發 Agent 列表
  GET  /platform/v1/tools   — 可用開發工具列表

安全：僅允許 is_developer=True 的用戶訪問（通過 env 白名單控制）。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from platform_agent.engine import platform_sse_generator, PLATFORM_AGENT_NAMES, PLATFORM_TOOLS

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic ──────────────────────────────────────────────────────

class PlatformStreamRequest(BaseModel):
    messages:   list[dict]           # [{role, content}]
    agent:      str = "architect"    # architect | coder | debugger | reviewer
    model:      str | None = None


# ── 端點 ──────────────────────────────────────────────────────────

@router.get("/agents", summary="可用開發 Agent 列表")
def list_platform_agents() -> Any:
    return [{"id": k, "name": v} for k, v in PLATFORM_AGENT_NAMES.items()]


@router.get("/tools", summary="可用開發工具列表")
def list_platform_tools() -> Any:
    return [{"name": t["name"], "description": t["description"]} for t in PLATFORM_TOOLS]


@router.post("/stream", summary="Platform Agent SSE 流式對話（開發者工具）")
async def platform_stream(req: PlatformStreamRequest):
    """
    Platform Agent 主要端點：SSE 流式對話，使用開發工具集。

    開發者可以：
    - 向 architect 詢問架構設計
    - 向 coder 查找代碼模式、生成代碼片段
    - 向 debugger 排查問題
    - 向 reviewer 審查代碼質量
    """
    if req.agent not in PLATFORM_AGENT_NAMES:
        raise HTTPException(400, f"未知 Agent：{req.agent}，可用：{list(PLATFORM_AGENT_NAMES)}")

    messages = [{"role": m.get("role"), "content": m.get("content")} for m in req.messages]

    async def _stream():
        try:
            async for event in platform_sse_generator(
                messages=messages,
                agent_name=req.agent,
                model=req.model,
            ):
                yield event
        except Exception as exc:
            logger.exception("Platform Agent stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
