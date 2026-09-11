"""MCP Tool Connectivity Layer. Does not replace RiskEngine."""
from __future__ import annotations

from typing import Any

MCP_ROLE = "Tool Connectivity Layer"
MCP_RUNTIME = "4_mcp"
REPLACES_RISKENGINE = False

CAPABILITIES: dict[str, dict[str, Any]] = {
    "Market Data": {
        "server": "wind",
        "tools": [
            "wind_get_price",
            "wind_get_fx",
            "wind_get_bond_info",
            "wind_get_index_components",
            "wind_get_yield_curve",
        ],
    },
    "Portfolio": {
        "server": "internal",
        "tools": ["get_positions", "get_fund_list", "get_context"],
    },
    "Risk": {
        "server": "internal",
        "tools": ["get_risk_snapshot"],
        "calculates": False,
        "note": "connectivity to stored snapshots; VaR / stress belong to RiskEngine",
    },
    "Valuation": {
        "server": "internal",
        "tools": ["get_nav_history"],
        "calculates": False,
        "note": "NAV history connectivity; pricing belongs to RiskEngine",
    },
    "SQL": {
        "server": "internal",
        "tools": ["query_business_db"],
        "readonly": True,
    },
}

FORBIDDEN_CALCULATIONS = ("NAV", "VaR", "PnL", "Stress Loss", "Valuation", "Risk Limit")

CAPABILITY_BY_TOOL = {
    "mcp.market_data": "Market Data",
    "mcp.portfolio": "Portfolio",
    "mcp.risk": "Risk",
    "mcp.valuation": "Valuation",
    "mcp.sql": "SQL",
}


def catalog() -> dict[str, Any]:
    return {
        "role": MCP_ROLE,
        "runtime": MCP_RUNTIME,
        "replaces_riskengine": REPLACES_RISKENGINE,
        "capabilities": list(CAPABILITIES),
        "forbidden_calculations": list(FORBIDDEN_CALCULATIONS),
    }


def connect(capability: str, *, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if capability not in CAPABILITIES:
        return {
            "ok": False,
            "error": {"code": "MCP", "message": f"unknown capability: {capability}"},
            "layer": MCP_ROLE,
            "replaces_riskengine": False,
        }
    spec = CAPABILITIES[capability]
    args = dict(arguments or {})
    requested = str(args.get("calculate") or args.get("metric") or "")
    if requested and requested in FORBIDDEN_CALCULATIONS:
        return refuse_calculate(requested)
    return {
        "ok": True,
        "layer": MCP_ROLE,
        "runtime": MCP_RUNTIME,
        "replaces_riskengine": False,
        "capability": capability,
        "server": spec["server"],
        "tools": list(spec["tools"]),
        "calculates": bool(spec.get("calculates", False)),
        "note": spec.get("note") or "connectivity only",
        "arguments": args,
    }


def refuse_calculate(metric: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "MCP_NOT_ENGINE",
            "message": f"MCP must not calculate {metric}; use RiskEngine via Business API",
        },
        "layer": MCP_ROLE,
        "replaces_riskengine": False,
        "metric": metric,
    }
