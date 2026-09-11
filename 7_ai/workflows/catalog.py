"""Named workflows. Each step is a tool call, never a local calculation."""
from __future__ import annotations

from importlib import import_module
from typing import Any

WORKFLOWS: dict[str, tuple[str, ...]] = {
    "morning_brief": ("investment.kpis", "risk.var", "risk.stress"),
    "valuation_close": ("valuation.price", "operations.nav", "operations.pnl"),
}


def catalog() -> dict[str, Any]:
    return {
        "workflows": {name: list(steps) for name, steps in WORKFLOWS.items()},
        "legacy_runtime": "autorisk/",
        "calculates": False,
    }


def run(name: str, context: Any) -> dict[str, Any]:
    steps = WORKFLOWS.get(name)
    if steps is None:
        return {"ok": False, "error": {"code": "WORKFLOW", "message": f"unknown workflow: {name}"}}
    dispatch = import_module("7_ai.tools.handlers").dispatch
    results = []
    for tool in steps:
        results.append({"tool": tool, "payload": dispatch(tool, context, {})})
    return {"ok": True, "workflow": name, "steps": results, "is_live": False}
