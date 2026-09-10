"""Portfolio Agent — Simulation Portfolio before any Live change."""

from ..base import AgentSpec

SPEC = AgentSpec(
    name="portfolio_agent",
    title="Portfolio Agent",
    tools=("portfolio.simulate", "portfolio.optimize", "portfolio.apply_live", "mcp.portfolio"),
    default_intent="portfolio.simulate",
    min_role="analyst",
)
