"""Workflow Agent — deterministic sequences over other tools."""

from ..base import AgentSpec

SPEC = AgentSpec(
    name="workflow_agent",
    title="Workflow Agent",
    tools=("workflow.run", "investment.kpis", "risk.var", "risk.stress", "mcp.sql"),
    default_intent="workflow.run",
    min_role="analyst",
)
