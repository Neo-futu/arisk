"""Agent Mode Router — 觸發 Claude Managed Agent 執行複雜任務。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import anthropic
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

router = APIRouter()
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# 任務狀態存儲（生產環境應用 Redis）
_tasks: dict[str, dict] = {}


class AgentTaskRequest(BaseModel):
    task: str
    fund_id: str | None = None
    date: str | None = None
    mode: str = "agent"  # agent | chat


class AgentTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/run", response_model=AgentTaskResponse)
async def run_agent_task(
    request: AgentTaskRequest,
    background_tasks: BackgroundTasks,
):
    """
    觸發 Agent 執行複雜分析任務（非同步）。
    返回 task_id，用 GET /agent/status/{task_id} 輪詢結果。
    """
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "request": request.model_dump(),
    }

    background_tasks.add_task(_run_agent_background, task_id, request)
    return AgentTaskResponse(task_id=task_id, status="queued", message="任務已加入隊列")


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查詢 Agent 任務狀態和結果。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/chat")
async def chat_with_agent(request: AgentTaskRequest):
    """
    同步 Chat 模式：直接與 Claude 對話（短查詢，不走 Agent 框架）。
    適合 ≤30s 的簡單問答。
    """
    context = _build_context(request)
    response = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=(
            "你是 FSI Risk Platform 的助手，幫助分析基金風控數據。"
            "回答要簡潔、結構化。如需詳細計算，建議使用 /agent/run 觸發完整 Agent 分析。"
        ),
        messages=[{"role": "user", "content": context}],
    )
    return {"reply": response.content[0].text, "model": ANTHROPIC_MODEL}


async def _run_agent_background(task_id: str, request: AgentTaskRequest) -> None:
    """後台執行 Agent 任務（實際生產應用 Celery 或 Managed Agent API）。"""
    try:
        _tasks[task_id]["status"] = "running"
        context = _build_context(request)

        response = _client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            system=(
                "你是 FSI Risk Platform 的 Risk Agent。執行用戶指定的風控分析任務。"
                "可調用的 API: Processing API (http://localhost:8001)，需要 X-API-Key 頭。"
                "按 risk-analysis 和 mmf-compliance SKILL 格式輸出報告。"
            ),
            messages=[{"role": "user", "content": context}],
        )

        _tasks[task_id].update({
            "status": "completed",
            "result": response.content[0].text,
            "completed_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        _tasks[task_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat(),
        })


def _build_context(request: AgentTaskRequest) -> str:
    parts = [request.task]
    if request.fund_id:
        parts.append(f"基金 ID: {request.fund_id}")
    if request.date:
        parts.append(f"日期: {request.date}")
    return "\n".join(parts)
