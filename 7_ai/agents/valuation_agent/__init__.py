"""Valuation Agent — price / NAV / PnL via Business + RiskEngine."""

from ..base import AgentSpec

SPEC = AgentSpec(
    name="valuation_agent",
    title="Valuation Agent",
    tools=("valuation.price", "operations.nav", "operations.pnl", "mcp.valuation"),
    default_intent="valuation.price",
    min_role="viewer",
)
