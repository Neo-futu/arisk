"""
6_entry/web/routers/agent_v2.py — AI Agent V2 路由器

整合 aiagent/ 四層架構：
  Layer 1 (Brain):       Planner 任務規劃 + Reflector 自我反思
  Layer 2 (Memory):      ContextManager 上下文 + VectorStore RAG
  Layer 3 (Tools):       8 個業務工具（含 knowledge_search）
  Layer 4 (Orchestration): Supervisor 多 Agent 路由 + TaskState Redis 狀態機

端點：
  POST /agent/v2/stream        — SSE 流式 + tool_use（主要端點）
  POST /agent/v2/task          — 提交異步長任務（返回 task_id）
  GET  /agent/v2/task/{id}     — 查詢任務狀態
  POST /agent/v2/chat          — 非流式 chat（兼容舊版）
  GET  /agent/v2/agents        — 可用 Agent 列表
  GET  /agent/v2/models        — 可用模型列表
  GET  /agent/v2/tools         — 工具清單

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
    session_id: str | None = None     # Layer 2: 記憶關聯的會話 ID
    user_id:    str | None = None     # Layer 2: 用戶 ID（情景記憶歸屬）


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
            session_id=req.session_id,
            user_id=req.user_id,
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


# ── Layer 4: 異步任務端點（Celery + Redis 狀態機） ─────────────────

class AsyncTaskRequest(BaseModel):
    message:    str
    agent:      str = "general"
    context:    dict | None = None
    model:      str | None = None
    session_id: str | None = None
    user_id:    str | None = None


@router.post("/task", summary="提交異步長任務（Layer 4 — Celery + Redis 狀態機）")
async def submit_task(req: AsyncTaskRequest):
    """
    提交需要較長時間的 Agent 任務（>30s）到 Celery 隊列。
    返回 task_id，客戶端通過 GET /task/{id} 輪詢狀態。

    Layer 4:
      - Celery 提供持久化、重試、超時控制（優於 asyncio.create_task）
      - Redis TaskState 提供實時狀態追蹤和日誌
      - 降級：若 Celery 不可用，回退到 asyncio.create_task
    """
    if req.agent not in AGENT_NAMES:
        raise HTTPException(400, f"未知 Agent：{req.agent}")

    from aiagent.orchestrator.task_state import TaskState, TaskStatus
    import asyncio

    ts = await TaskState.create(
        agent_id=req.agent,
        query=req.message,
        model_id=req.model or DEFAULT_MODEL,
        session_id=req.session_id,
        user_id=req.user_id,
    )
    await ts.log(f"任務已提交，Agent: {req.agent}, Model: {req.model or DEFAULT_MODEL}")

    # 優先使用 Celery（Layer 4 持久化編排）
    celery_dispatched = False
    try:
        import importlib
        tasks_mod = importlib.import_module("2_processing.workers.tasks")
        run_agent_task = tasks_mod.run_agent_task
        messages = [{"role": "user", "content": req.message}]
        run_agent_task.apply_async(
            kwargs={
                "task_id":    ts.task_id,
                "agent_name": req.agent,
                "model_id":   req.model or DEFAULT_MODEL,
                "messages":   messages,
                "context":    req.context,
                "session_id": req.session_id,
                "user_id":    req.user_id,
            },
            task_id=ts.task_id,
            expires=3600,
        )
        celery_dispatched = True
        await ts.log("已提交到 Celery Worker 執行")
    except Exception as exc:
        logger.warning("[agent_v2] Celery not available, fallback to asyncio: %s", exc)

    # 降級：Celery 不可用時使用 asyncio.create_task
    if not celery_dispatched:
        async def _run_background():
            try:
                await ts.transition(TaskStatus.PLANNING)
                messages = [{"role": "user", "content": req.message}]
                result_parts: list[str] = []
                tool_calls: list[dict]  = []

                await ts.transition(TaskStatus.EXECUTING)
                async for event in run_agent(
                    messages=messages,
                    agent_name=req.agent,
                    context=req.context,
                    model=req.model,
                    session_id=req.session_id,
                    user_id=req.user_id,
                ):
                    if event.get("type") == "text":
                        result_parts.append(event.get("content", ""))
                    elif event.get("type") == "tool_call":
                        tool_calls.append({"name": event.get("name"), "input": event.get("input")})
                        await ts.log(f"工具調用: {event.get('name')}")
                    elif event.get("type") == "error":
                        await ts.fail(event.get("message", "未知錯誤"))
                        return

                await ts.transition(TaskStatus.REFLECTING)
                await ts.complete({
                    "reply":      "".join(result_parts),
                    "tool_calls": tool_calls,
                    "agent":      req.agent,
                    "model":      req.model or DEFAULT_MODEL,
                })
                await ts.log("任務成功完成（asyncio 模式）")
            except Exception as exc:
                await ts.fail(str(exc)[:300])

        asyncio.create_task(_run_background())

    return {"task_id": ts.task_id, "status": "queued", "message": "任務已提交，請通過 GET /task/{id} 查詢進度"}


@router.get("/task/{task_id}", summary="查詢異步任務狀態")
async def get_task_status(task_id: str):
    """查詢異步任務的當前狀態和結果。"""
    from aiagent.orchestrator.task_state import TaskState

    ts = await TaskState.load(task_id)
    if not ts:
        raise HTTPException(404, f"任務不存在或已過期：{task_id}")

    status_data = await ts.get_status()
    result      = await ts.get_result() if status_data.get("status") == "done" else None
    logs        = await ts.get_logs(limit=20)

    return {
        **status_data,
        "result": result,
        "logs":   logs,
    }


@router.get("/tools", summary="查詢工具清單")
def list_tools():
    """返回 Agent 可調用的工具列表（供調試和文檔）。"""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in TOOLS
    ]
