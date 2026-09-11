"""Unified quantitative and risk calculation platform (RiskEngine)."""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RISKENGINE_NAME",
    "RISKENGINE_VERSION",
    "RiskEngine",
    "limits",
    "risk",
    "validation",
    "valuation",
    "liquidity",
    "counterparty",
    "pnl",
    "stress",
    "scenario",
    "instruments",
    "market",
    "products",
    "models",
    "utils",
    "portfolio",
    "trade",
    "governance",
]


def __getattr__(name: str) -> Any:
    if name in {"RISKENGINE_NAME", "RISKENGINE_VERSION"}:
        return getattr(import_module("3_riskengine.core.lineage"), name)
    if name == "RiskEngine":
        return import_module("3_riskengine.core.engine").RiskEngine
    if name in {
        "limits",
        "risk",
        "validation",
        "valuation",
        "liquidity",
        "counterparty",
        "pnl",
        "stress",
        "scenario",
        "instruments",
        "market",
        "products",
        "models",
        "utils",
        "portfolio",
        "trade",
        "governance",
    }:
        return import_module(f"3_riskengine.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
