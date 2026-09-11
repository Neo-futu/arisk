"""Agent identity and authorization. Agents cannot bypass these gates."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from importlib import import_module


class AgentAuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"agent.read"}),
    "analyst": frozenset({"agent.read", "portfolio.simulate", "portfolio.optimize", "quant.read", "workflow.run"}),
    "pm": frozenset(
        {
            "agent.read",
            "portfolio.simulate",
            "portfolio.optimize",
            "portfolio.apply_live",
            "quant.read",
            "workflow.run",
        }
    ),
    "admin": frozenset(
        {
            "agent.read",
            "portfolio.simulate",
            "portfolio.optimize",
            "portfolio.apply_live",
            "quant.read",
            "workflow.run",
        }
    ),
}

TOOL_PERMISSIONS: dict[str, str] = {
    "investment.kpis": "agent.read",
    "investment.exposure": "agent.read",
    "portfolio.simulate": "portfolio.simulate",
    "portfolio.optimize": "portfolio.optimize",
    "portfolio.apply_live": "portfolio.apply_live",
    "risk.var": "agent.read",
    "risk.cvar": "agent.read",
    "risk.stress": "agent.read",
    "risk.limits": "agent.read",
    "valuation.price": "agent.read",
    "operations.nav": "agent.read",
    "operations.pnl": "agent.read",
    "testing.run": "agent.read",
    "mcp.market_data": "agent.read",
    "mcp.portfolio": "agent.read",
    "mcp.risk": "agent.read",
    "mcp.valuation": "agent.read",
    "mcp.sql": "agent.read",
    "workflow.run": "workflow.run",
}


def default_audit():
    return import_module("4_business.risk_governance.audit_log").default_audit()


@dataclass
class AgentContext:
    actor: str = "system"
    jwt_present: bool = True
    jwt_valid: bool = True
    role: str = "analyst"
    portfolio_authorized: bool = True
    api_authorized: bool = True
    authorized_funds: frozenset[str] = field(default_factory=lambda: frozenset({"TEST001", "QUANT"}))
    permissions: frozenset[str] | None = None
    snapshot: Any = None
    fund_id: str | None = None
    audit: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.permissions is None:
            self.permissions = ROLE_PERMISSIONS.get(self.role, frozenset())
        if self.audit is None:
            self.audit = default_audit()

    @property
    def effective_fund(self) -> str | None:
        if self.fund_id:
            return self.fund_id
        snapshot = self.snapshot
        return getattr(snapshot, "fund_id", None)


def guard_identity(context: AgentContext) -> None:
    if not context.jwt_present:
        raise AgentAuthError("JWT", "JWT is required")
    if not context.jwt_valid:
        raise AgentAuthError("JWT", "JWT is invalid")
    if not context.api_authorized:
        raise AgentAuthError("API", "API authorization failed")
    if context.role not in ROLE_PERMISSIONS:
        raise AgentAuthError("ROLE", f"unknown role: {context.role}")


def guard_portfolio(context: AgentContext, fund_id: str | None) -> None:
    if not fund_id:
        return
    if not context.portfolio_authorized:
        raise AgentAuthError("PORTFOLIO", "portfolio authorization denied")
    if fund_id not in context.authorized_funds:
        raise AgentAuthError("PORTFOLIO", f"fund {fund_id} is not authorized")


def guard_tool(context: AgentContext, tool_name: str) -> None:
    required = TOOL_PERMISSIONS.get(tool_name)
    if required is None:
        raise AgentAuthError("PERMISSION", f"unknown tool: {tool_name}")
    if required not in (context.permissions or frozenset()):
        raise AgentAuthError("PERMISSION", f"missing permission: {required}")
