"""platform_agent orchestrator supervisor.

Routes incoming requests to scheduler / monitor / etl-coordinator.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_ROUTING_RULES: list[tuple[str, str]] = [
    (r"排程|調度|schedule|cron|beat|任務編排|workflow", "scheduler"),
    (r"健康|監控|告警|異常|health|monitor|alert", "monitor"),
    (r"ETL|載入|同步|refresh|補數|數據質量|data quality", "etl-coordinator"),
]

_MULTI_STAGE_RULES: list[tuple[str, list[str]]] = [
    (r"日終|EOD|end.?of.?day|收盤", ["etl-coordinator", "scheduler", "monitor"]),
    (r"全流程|完整流程|full workflow", ["etl-coordinator", "scheduler", "monitor"]),
]


def route_to_platform_agent(user_message: str, current_agent: str = "scheduler") -> str:
    """Heuristic route for platform agent roles."""
    if current_agent in {"scheduler", "monitor", "etl-coordinator"}:
        return current_agent

    for pattern, target in _ROUTING_RULES:
        if re.search(pattern, user_message, re.IGNORECASE):
            logger.info("[PlatformSupervisor] route -> %s", target)
            return target
    return "scheduler"


def multi_stage_chain(user_message: str) -> list[str] | None:
    """Return an execution chain when a multi-stage workflow is detected."""
    for pattern, chain in _MULTI_STAGE_RULES:
        if re.search(pattern, user_message, re.IGNORECASE):
            return chain
    return None


class PlatformSupervisor:
    """Supervisor for optional multi-stage platform workflows."""

    def __init__(self) -> None:
        self._max_handoffs = 3

    async def run(
        self,
        messages: list[dict],
        agent_name: str,
        model: str | None,
        stream_fn,
    ):
        user_query = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        chain = multi_stage_chain(user_query)

        if not chain:
            async for event in stream_fn(messages=messages, agent_name=agent_name, model=model):
                yield event
            return

        yield {"type": "supervisor", "message": f"多階段任務：{' -> '.join(chain)}"}

        for idx, role in enumerate(chain):
            if idx >= self._max_handoffs:
                break
            if idx > 0:
                yield {"type": "handoff", "from": chain[idx - 1], "to": role}
            async for event in stream_fn(messages=messages, agent_name=role, model=model):
                if event.get("type") not in {"start", "done"}:
                    yield event
