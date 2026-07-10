"""
aiagent/engine/stream.py — SSE 流式輸出封裝（Layer 1+2+3 整合點）

將 runner.run_agent() 的 async generator 封裝為 FastAPI StreamingResponse 兼容的
SSE（Server-Sent Events）格式。

Layer 整合點：
  Layer 1 (Brain):   注入 Planner 生成的執行計劃；Reflector 在完成後評估輸出
  Layer 2 (Memory):  傳入 session_id / user_id 供 runner 保存情景記憶
  Layer 3 (Tools):   通過 runner 透傳

SSE 事件格式：
  data: {"type": "start",       "agent": "...", "model": "...", "plan": {...}}
  data: {"type": "plan",        "steps": [...]}          ← 新增：計劃步驟
  data: {"type": "text",        "content": "..."}
  data: {"type": "tool_call",   "name": "...", "input": {...}, "id": "..."}
  data: {"type": "tool_result", "name": "...", "result": {...}, "id": "..."}
  data: {"type": "reflection",  "issue": "...", "suggestion": "..."}  ← 新增
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
    messages:   list[dict],
    agent_name: str,
    context:    dict | None = None,
    jwt_token:  str | None = None,
    model:      str | None = None,
    session_id: str | None = None,
    user_id:    str | None = None,
) -> AsyncIterator[str]:
    """
    FastAPI StreamingResponse 的異步生成器。

    Layer 1 — Planner：複雜任務先生成執行計劃並推送給前端
    Layer 1 — Reflector：輸出完成後評估質量，推送反思事件
    Layer 2 — Memory：session_id/user_id 傳入 runner 保存情景記憶
    """
    selected = model or DEFAULT_MODEL
    user_query = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # ── Layer 1: Planner — 複雜任務先規劃 ────────────────────────
    plan = None
    plan_injection = ""
    try:
        from .planner import create_plan, plan_to_system_injection
        plan = await create_plan(user_query, agent_name, model=selected)
        if plan:
            plan_injection = plan_to_system_injection(plan)
            yield _sse({"type": "plan", "title": plan["title"], "steps": plan["steps"]})
    except Exception as exc:
        logger.debug("[stream] planner skipped: %s", exc)

    yield _sse({"type": "start", "agent": agent_name, "model": selected})

    # ── 注入計劃到 context ────────────────────────────────────────
    effective_context = dict(context or {})
    if plan_injection:
        effective_context["_plan"] = plan_injection

    # ── 執行主 ReAct 循環 ─────────────────────────────────────────
    agent_output_parts: list[str] = []
    tool_results_collected: list[dict] = []

    try:
        async for event in run_agent(
            messages,
            agent_name,
            effective_context,
            jwt_token,
            model=selected,
            session_id=session_id,
            user_id=user_id,
        ):
            # 收集輸出用於後續反思
            if event.get("type") == "text" and event.get("content"):
                agent_output_parts.append(event["content"])
            elif event.get("type") == "tool_result":
                tool_results_collected.append({
                    "name":   event.get("name"),
                    "result": event.get("result"),
                })

            yield _sse(event)

            if event.get("type") == "error":
                yield _sse({"type": "done"})
                return
            if event.get("type") == "done":
                # ── Layer 1: Reflector — 輸出後反思 ───────────────
                try:
                    from .reflector import detect_issues
                    agent_output = "".join(agent_output_parts)
                    reflection = detect_issues(agent_output, tool_results_collected)
                    if reflection.has_issue:
                        yield _sse({
                            "type":        "reflection",
                            "issue_type":  reflection.issue_type,
                            "description": reflection.description,
                            "suggestion":  reflection.suggestion,
                        })
                        logger.info("[stream] reflection: %s — %s", reflection.issue_type, reflection.description)
                except Exception as exc:
                    logger.debug("[stream] reflector skipped: %s", exc)
                return

    except Exception as exc:
        logger.exception("SSE stream error for agent=%s model=%s", agent_name, selected)
        yield _sse({"type": "error", "message": f"流式輸出異常：{exc}"})

    yield _sse({"type": "done"})
