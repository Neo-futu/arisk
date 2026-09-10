"""Agent tool registry — names only; execution is in handlers."""
from __future__ import annotations

from typing import Any

from .handlers import HANDLERS, dispatch
from .mcp_layer import catalog as mcp_catalog

TOOL_NAMES = tuple(HANDLERS)


def catalog() -> dict[str, Any]:
    return {
        "tools": list(TOOL_NAMES),
        "mcp": mcp_catalog(),
        "calculates": False,
        "business_api": "4_business / 5_integrations.quant",
        "engine": "3_riskengine",
    }


__all__ = ["TOOL_NAMES", "catalog", "dispatch"]
