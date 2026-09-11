"""Investment Agent — KPIs and exposure via Business API."""

from ..base import AgentSpec

SPEC = AgentSpec(
    name="investment_agent",
    title="Investment Agent",
    tools=("investment.kpis", "investment.exposure", "mcp.market_data"),
    default_intent="investment.kpis",
    min_role="viewer",
)
