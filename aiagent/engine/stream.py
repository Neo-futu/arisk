"""
aiagent/engine/stream.py — SSE 流式輸出封裝（支持多模型）

將 runner.run_agent() 的 async generator 封裝為 FastAPI StreamingResponse 兼容的
SSE（Server-Sent Events）格式。

SSE 事件格式：
  data: {"type": "start",       "agent": "...", "model": "..."}
  data: {"type": "text",        "content": "..."}
  data: {"type": "tool_call",   "name": "...", "input": {...}, "id": "..."}
  data: {"type": "tool_result", "name": "...", "result": {...}, "id": "..."}
  data: {"type": "error",       "message": "..."}
  data: {"type": "done"}

前端使用 fetch + ReadableStream 接收（不使用 EventSource，因為需要 POST + body）。
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from .runner import run_agent, DEFAULT_MODEL

logger = logging.getLogger(__name__)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def sse_generator(
    messages: list[dict],
    agent_name: str,
    context: dict | None = None,
    jwt_token: str | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """
    FastAPI StreamingResponse 的異步生成器，支持多模型。

    用法：
        return StreamingResponse(
            sse_generator(messages, agent_name, context, jwt_token, model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    """
    selected = model or DEFAULT_MODEL
    yield _sse({"type": "start", "agent": agent_name, "model": selected})

    try:
        async for event in run_agent(messages, agent_name, context, jwt_token, model=selected):
            yield _sse(event)
            if event.get("type") == "error":
                yield _sse({"type": "done"})
                return
            if event.get("type") == "done":
                return
    except Exception as exc:
        logger.exception("SSE stream error for agent=%s model=%s", agent_name, selected)
        yield _sse({"type": "error", "message": f"流式輸出異常：{exc}"})

    yield _sse({"type": "done"})
