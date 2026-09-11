"""AI layer — unified natural language and workflow interface."""
from __future__ import annotations

from importlib import import_module
from typing import Any

CHAIN = (
    "User",
    "Agent",
    "Intent",
    "Tool",
    "Business API",
    "RiskEngine",
    "FinancePy / Riskfolio / ORE",
    "Result",
    "Agent Explanation",
)

FORBIDDEN_CALCULATIONS = ("NAV", "VaR", "PnL", "Stress Loss", "Valuation", "Risk Limit")


def catalog() -> dict[str, Any]:
    return import_module("7_ai.runtime").catalog()


def run(message: str, **kwargs: Any) -> dict[str, Any]:
    return import_module("7_ai.runtime").run(message, **kwargs)


def stream(message: str, **kwargs: Any):
    return import_module("7_ai.runtime").stream(message, **kwargs)


__all__ = ["CHAIN", "FORBIDDEN_CALCULATIONS", "catalog", "run", "stream"]
