"""7_ai.agents — NL interface. Runtime authority for existing chat remains aiagent/."""
from __future__ import annotations

from importlib import import_module
from typing import Any

from .base import AgentSpec

AGENT_MODULES = (
    "investment_agent",
    "portfolio_agent",
    "risk_agent",
    "valuation_agent",
    "workflow_agent",
)


def _load(name: str) -> AgentSpec:
    return import_module(f"7_ai.agents.{name}").SPEC


AGENTS: dict[str, AgentSpec] = {name: _load(name) for name in AGENT_MODULES}


def get(name: str) -> AgentSpec:
    try:
        return AGENTS[name]
    except KeyError as exc:
        known = ", ".join(AGENT_MODULES)
        raise KeyError(f"unknown agent {name!r}. Known: {known}") from exc


def catalog() -> dict[str, Any]:
    return {
        "agents": {
            name: {
                "title": spec.title,
                "tools": list(spec.tools),
                "default_intent": spec.default_intent,
                "min_role": spec.min_role,
            }
            for name, spec in AGENTS.items()
        },
        "legacy_runtime": "aiagent/",
    }


__all__ = ["AGENT_MODULES", "AGENTS", "AgentSpec", "catalog", "get"]
