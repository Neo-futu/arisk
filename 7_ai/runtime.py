"""Agent kernel: User → Agent → Intent → Tool → Business → RiskEngine → Explanation."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Iterator, Mapping

from .auth import AgentAuthError, AgentContext, guard_identity, guard_portfolio, guard_tool
from .explain import explain
from .intent import Intent, parse

CHAIN = (
    "User",
    "Agent",
    "Intent",
    "Tool",
    "Business API",
    "RiskEngine",
    "FinancePy / Riskfolio / ORE",
    "Result",
    "Agent Explanation",
)

FORBIDDEN_CALCULATIONS = ("NAV", "VaR", "PnL", "Stress Loss", "Valuation", "Risk Limit")

INTENT_AGENT = {
    "investment.kpis": "investment_agent",
    "investment.exposure": "investment_agent",
    "portfolio.simulate": "portfolio_agent",
    "portfolio.optimize": "portfolio_agent",
    "portfolio.apply_live": "portfolio_agent",
    "risk.var": "risk_agent",
    "risk.cvar": "risk_agent",
    "risk.stress": "risk_agent",
    "risk.limits": "risk_agent",
    "testing.run": "risk_agent",
    "valuation.price": "valuation_agent",
    "operations.nav": "valuation_agent",
    "operations.pnl": "valuation_agent",
    "mcp.market_data": "investment_agent",
    "mcp.portfolio": "portfolio_agent",
    "mcp.risk": "risk_agent",
    "mcp.valuation": "valuation_agent",
    "mcp.sql": "workflow_agent",
    "workflow.run": "workflow_agent",
}


def catalog() -> dict[str, Any]:
    agents = import_module("7_ai.agents")
    tools = import_module("7_ai.tools")
    mcp = import_module("7_ai.tools.mcp_layer")
    skills = import_module("7_ai.skills")
    workflows = import_module("7_ai.workflows")
    knowledge = import_module("7_ai.knowledge")
    return {
        "chain": list(CHAIN),
        "forbidden_calculations": list(FORBIDDEN_CALCULATIONS),
        "agents": agents.catalog()["agents"],
        "tools": tools.catalog(),
        "mcp": mcp.catalog(),
        "skills": skills.catalog(),
        "workflows": workflows.catalog(),
        "knowledge": knowledge.catalog(),
        "legacy": {"agents": "aiagent/", "mcp": "4_mcp/", "skills": "3_skills/", "workflows": "autorisk/"},
    }


def _resolve_agent(name: str | None, intent: Intent) -> Any:
    agents = import_module("7_ai.agents")
    chosen = name or INTENT_AGENT.get(intent.name) or "investment_agent"
    return agents.get(chosen)


def stream(
    message: str,
    *,
    agent: str | None = None,
    context: AgentContext | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    ctx = context or AgentContext()
    yield {"event": "session_start", "chain": list(CHAIN)}
    try:
        guard_identity(ctx)
        yield {"event": "auth", "ok": True, "actor": ctx.actor, "role": ctx.role}
    except AgentAuthError as exc:
        yield _failure(exc.code, str(exc))
        _audit(ctx, "AGENT_AUTH", ok=False, code=exc.code, message=str(exc))
        yield {"event": "session_end", "ok": False}
        return

    intent = parse(message, agent=agent, extra=dict(extra or {}))
    if not intent.tool:
        yield _failure("INTENT", "could not resolve intent")
        _audit(ctx, "AGENT_INTENT", ok=False, message=message)
        yield {"event": "session_end", "ok": False}
        return

    try:
        spec = _resolve_agent(agent, intent)
    except KeyError as exc:
        yield _failure("AGENT", str(exc))
        yield {"event": "session_end", "ok": False}
        return

    if intent.tool not in spec.tools:
        yield _failure("AGENT_SCOPE", f"{spec.name} cannot run {intent.tool}")
        _audit(ctx, "AGENT_SCOPE", ok=False, agent=spec.name, tool=intent.tool)
        yield {"event": "session_end", "ok": False}
        return

    yield {"event": "agent", "name": spec.name, "title": spec.title}
    yield {"event": "intent", "name": intent.name, "tool": intent.tool, "confidence": intent.confidence}

    fund_id = ctx.effective_fund
    try:
        guard_portfolio(ctx, fund_id)
        guard_tool(ctx, intent.tool)
    except AgentAuthError as exc:
        yield _failure(exc.code, str(exc))
        _audit(ctx, "AGENT_AUTH", ok=False, code=exc.code, message=str(exc), agent=spec.name)
        yield {"event": "session_end", "ok": False}
        return

    yield {"event": "context", "fund_id": fund_id, "role": ctx.role, "actor": ctx.actor}
    yield {"event": "tool_start", "tool": intent.tool}

    handlers = import_module("7_ai.tools.handlers")
    tool_args = {**ctx.extra, **intent.args}
    try:
        payload = handlers.dispatch(intent.tool, ctx, tool_args)
    except handlers.ToolError as exc:
        yield _failure(exc.code, str(exc))
        _audit(ctx, "AGENT_TOOL", ok=False, code=exc.code, message=str(exc), agent=spec.name, tool=intent.tool)
        yield {"event": "session_end", "ok": False}
        return
    except Exception as exc:  # noqa: BLE001 — surface business/engine failures to the agent
        yield _failure("FAILURE", str(exc)[:300])
        _audit(ctx, "AGENT_TOOL", ok=False, code="FAILURE", message=str(exc)[:300], agent=spec.name, tool=intent.tool)
        yield {"event": "session_end", "ok": False}
        return

    yield {"event": "tool_end", "tool": intent.tool}
    if payload.get("ok") is False:
        err = payload.get("error") or {"code": "FAILURE", "message": "tool returned not ok"}
        yield _failure(str(err.get("code") or "FAILURE"), str(err.get("message") or "tool returned not ok"))
        _audit(
            ctx,
            "AGENT_TOOL",
            ok=False,
            code=err.get("code"),
            message=str(err.get("message") or "")[:300],
            agent=spec.name,
            tool=intent.tool,
        )
        yield {"event": "session_end", "ok": False}
        return
    yield {
        "event": "result",
        "ok": bool(payload.get("ok", True)),
        "payload": payload,
        "via": ["Business API", "RiskEngine"],
    }
    text = explain(spec.name, intent.name, {"ok": payload.get("ok", True), "payload": payload, "error": payload.get("error")})
    yield {"event": "explanation", "text": text}
    _audit(
        ctx,
        "AGENT_TURN",
        ok=bool(payload.get("ok", True)),
        agent=spec.name,
        intent=intent.name,
        tool=intent.tool,
        fund_id=fund_id,
    )
    yield {"event": "audit", "ok": True}
    yield {"event": "session_end", "ok": True, "chain": list(CHAIN)}


def run(
    message: str,
    *,
    agent: str | None = None,
    context: AgentContext | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    events = list(stream(message, agent=agent, context=context, extra=extra))
    result_event = next((item for item in events if item["event"] == "result"), None)
    fail_event = next((item for item in events if item["event"] == "failure"), None)
    explanation = next((item["text"] for item in events if item["event"] == "explanation"), "")
    agent_event = next((item for item in events if item["event"] == "agent"), None)
    intent_event = next((item for item in events if item["event"] == "intent"), None)
    ok = events[-1].get("ok") is True if events else False
    return {
        "ok": ok,
        "chain": list(CHAIN),
        "agent": None if agent_event is None else agent_event["name"],
        "intent": None if intent_event is None else intent_event["name"],
        "tool": None if intent_event is None else intent_event["tool"],
        "result": None if result_event is None else result_event["payload"],
        "explanation": explanation,
        "error": None if fail_event is None else fail_event["error"],
        "events": events,
        "calculates": False,
        "forbidden_calculations": list(FORBIDDEN_CALCULATIONS),
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"event": "failure", "ok": False, "error": {"code": code, "message": message}}


def _audit(context: AgentContext, event_type: str, **payload: Any) -> None:
    audit = context.audit
    if audit is None:
        return
    audit.record(event_type, actor=context.actor, payload=payload)
