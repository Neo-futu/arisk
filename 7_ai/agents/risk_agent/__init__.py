"""Risk Agent — VaR / CVaR / stress / limits via RiskEngine only."""

from ..base import AgentSpec

SPEC = AgentSpec(
    name="risk_agent",
    title="Risk Agent",
    tools=("risk.var", "risk.cvar", "risk.stress", "risk.limits", "testing.run", "mcp.risk"),
    default_intent="risk.var",
    min_role="viewer",
)
