"""SSE stream wrapper for platform agent with orchestration support."""
from __future__ import annotations

import json
from typing import AsyncIterator

from platform_agent.engine.platform_runner import run_platform_agent
from platform_agent.orchestrator.supervisor import PlatformSupervisor


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\\n\\n"


async def platform_sse_generator(
    messages: list[dict],
    agent_name: str,
    model: str | None = None,
) -> AsyncIterator[str]:
    supervisor = PlatformSupervisor()
    yield _sse({"type": "start", "agent": agent_name, "model": model})

    async for event in supervisor.run(
        messages=messages,
        agent_name=agent_name,
        model=model,
        stream_fn=run_platform_agent,
    ):
        yield _sse(event)
        if event.get("type") in {"error", "done"}:
            return

    yield _sse({"type": "done"})
