"""Tool handlers call Business API / Quant / MCP connectivity. No engine math here."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from . import mcp_layer


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _snapshot(context: Any) -> Any:
    snapshot = getattr(context, "snapshot", None)
    if snapshot is None:
        raise ToolError("CONTEXT", "missing portfolio snapshot")
    return snapshot


def _quant():
    return import_module("5_integrations.quant")


def _po():
    return import_module("4_business.portfolio_optimization.service")


def _ir():
    return import_module("4_business.investment_risk.service")


def _ops():
    return import_module("4_business.operations.service")


def investment_kpis(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    pack = _ir().compute_kpi_pack(_snapshot(context))
    return {"kpis": pack["kpis"], "engine": pack.get("engine"), "limit_engine": pack.get("limit_engine")}


def investment_exposure(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().risk.exposure(_snapshot(context))


def portfolio_simulate(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    label = str(args.get("label") or "agent")
    cloned = _po().clone_live(_snapshot(context), label=label)
    cloned["stage"] = "Simulation Portfolio"
    cloned["is_live"] = False
    context.extra["sim_id"] = cloned["sim_id"]
    return cloned


def portfolio_optimize(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    method = str(args.get("method") or "hrp")
    sim_id = args.get("sim_id") or context.extra.get("sim_id")
    if not sim_id:
        cloned = _po().clone_live(_snapshot(context), label="agent-optimize")
        sim_id = cloned["sim_id"]
        context.extra["sim_id"] = sim_id
    return _po().optimize_simulation(sim_id, method)


def portfolio_apply_live(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    sim_id = args.get("sim_id") or context.extra.get("sim_id")
    if not sim_id:
        raise ToolError("SIMULATION_REQUIRED", "Live Portfolio changes require a Simulation Portfolio first")
    authorized = "portfolio.apply_live" in (context.permissions or frozenset())
    if args.get("authorized") is False:
        authorized = False
    try:
        return _po().apply_to_live(str(sim_id), authorized=authorized)
    except PermissionError as exc:
        raise ToolError("PORTFOLIO", str(exc)) from exc


def risk_var(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().risk.var(_snapshot(context), confidence=float(args.get("confidence") or 0.99))


def risk_cvar(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().risk.cvar(_snapshot(context), confidence=float(args.get("confidence") or 0.99))


def risk_stress(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().risk.stress(_snapshot(context), scenario_id=str(args.get("scenario_id") or "gfc_2008"))


def risk_limits(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    pack = _ir().compute_kpi_pack(_snapshot(context))
    return {"limits": pack["limits"], "engine": pack.get("limit_engine")}


def valuation_price(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().valuation.price(_snapshot(context))


def operations_nav(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _ops().nav(_snapshot(context))


def operations_pnl(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _ops().pnl(_snapshot(context))


def testing_run(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    return _quant().testing.run(_snapshot(context), analytic=str(args.get("analytic") or "SENSITIVITY"))


def mcp_connect(context: Any, args: Mapping[str, Any], *, capability: str) -> dict[str, Any]:
    del context
    return mcp_layer.connect(capability, arguments=dict(args))


def workflow_run(context: Any, args: Mapping[str, Any]) -> dict[str, Any]:
    workflows = import_module("7_ai.workflows.catalog")
    name = str(args.get("workflow") or "morning_brief")
    return workflows.run(name, context)


HANDLERS = {
    "investment.kpis": investment_kpis,
    "investment.exposure": investment_exposure,
    "portfolio.simulate": portfolio_simulate,
    "portfolio.optimize": portfolio_optimize,
    "portfolio.apply_live": portfolio_apply_live,
    "risk.var": risk_var,
    "risk.cvar": risk_cvar,
    "risk.stress": risk_stress,
    "risk.limits": risk_limits,
    "valuation.price": valuation_price,
    "operations.nav": operations_nav,
    "operations.pnl": operations_pnl,
    "testing.run": testing_run,
    "mcp.market_data": lambda ctx, args: mcp_connect(ctx, args, capability="Market Data"),
    "mcp.portfolio": lambda ctx, args: mcp_connect(ctx, args, capability="Portfolio"),
    "mcp.risk": lambda ctx, args: mcp_connect(ctx, args, capability="Risk"),
    "mcp.valuation": lambda ctx, args: mcp_connect(ctx, args, capability="Valuation"),
    "mcp.sql": lambda ctx, args: mcp_connect(ctx, args, capability="SQL"),
    "workflow.run": workflow_run,
}


def dispatch(tool_name: str, context: Any, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    handler = HANDLERS.get(tool_name)
    if handler is None:
        raise ToolError("TOOL", f"unknown tool: {tool_name}")
    return handler(context, dict(args or {}))
