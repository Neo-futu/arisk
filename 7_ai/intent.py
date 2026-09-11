"""Rule-based intent parser. No calculations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    name: str
    tool: str
    confidence: float
    args: dict[str, Any] = field(default_factory=dict)


INTENT_TOOLS: dict[str, str] = {
    "investment.kpis": "investment.kpis",
    "investment.exposure": "investment.exposure",
    "portfolio.simulate": "portfolio.simulate",
    "portfolio.optimize": "portfolio.optimize",
    "portfolio.apply_live": "portfolio.apply_live",
    "risk.var": "risk.var",
    "risk.cvar": "risk.cvar",
    "risk.stress": "risk.stress",
    "risk.limits": "risk.limits",
    "valuation.price": "valuation.price",
    "operations.nav": "operations.nav",
    "operations.pnl": "operations.pnl",
    "testing.run": "testing.run",
    "mcp.market_data": "mcp.market_data",
    "mcp.portfolio": "mcp.portfolio",
    "mcp.risk": "mcp.risk",
    "mcp.valuation": "mcp.valuation",
    "mcp.sql": "mcp.sql",
    "workflow.run": "workflow.run",
}

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("portfolio.apply_live", ("apply live", "apply_to_live", "上线", "写入 live")),
    ("portfolio.optimize", ("optimize", "optimisation", "优化", "hrp", "risk parity")),
    ("portfolio.simulate", ("simulate", "simulation", "clone", "仿真仓", "仿真")),
    ("risk.limits", ("limit", "limits", "限额", "hard breach")),
    ("risk.cvar", ("cvar", "expected shortfall", "es ")),
    ("risk.var", ("var", "value at risk", "在险价值")),
    ("risk.stress", ("stress", "压力", "gfc")),
    ("operations.pnl", ("pnl", "p&l", "损益")),
    ("operations.nav", ("nav", "净值")),
    ("valuation.price", ("valuation", "price", "定价", "估值")),
    ("investment.exposure", ("exposure", "暴露", "集中度")),
    ("investment.kpis", ("kpi", "investment", "投资风险")),
    ("testing.run", ("testing", "sensitivity", "风险测试")),
    ("mcp.market_data", ("market data", "行情", "wind")),
    ("mcp.portfolio", ("mcp portfolio", "持仓查询")),
    ("mcp.risk", ("mcp risk",)),
    ("mcp.valuation", ("mcp valuation",)),
    ("mcp.sql", ("sql", "query_business_db")),
    ("workflow.run", ("workflow", "工作流", "morning brief")),
)

AGENT_DEFAULT_INTENT: dict[str, str] = {
    "investment_agent": "investment.kpis",
    "portfolio_agent": "portfolio.simulate",
    "risk_agent": "risk.var",
    "valuation_agent": "valuation.price",
    "workflow_agent": "workflow.run",
}


def parse(message: str, *, agent: str | None = None, extra: dict[str, Any] | None = None) -> Intent:
    text = (message or "").strip().lower()
    for name, keywords in _KEYWORDS:
        if any(token in text for token in keywords):
            return Intent(name=name, tool=INTENT_TOOLS[name], confidence=0.9, args=dict(extra or {}))
    if agent and agent in AGENT_DEFAULT_INTENT:
        name = AGENT_DEFAULT_INTENT[agent]
        return Intent(name=name, tool=INTENT_TOOLS[name], confidence=0.4, args=dict(extra or {}))
    return Intent(name="unknown", tool="", confidence=0.0, args=dict(extra or {}))
