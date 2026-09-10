"""Wave 8 Agent interface, tools, MCP connectivity, auth, audit, streaming."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

from .fixtures import sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
AI = import_module("7_ai")
AUTH = import_module("7_ai.auth")
AuditLog = import_module("4_business.risk_governance.audit_log").AuditLog

FORBIDDEN = ("3_riskengine", "financepy", "riskfolio", "QuantLib", "yfinance", "openbb")
AGENT_CODE_DIRS = (
    ROOT / "7_ai" / "agents",
    ROOT / "7_ai" / "runtime.py",
    ROOT / "7_ai" / "auth.py",
    ROOT / "7_ai" / "intent.py",
    ROOT / "7_ai" / "explain.py",
)


def _ctx(**kwargs):
    kwargs.setdefault("snapshot", sample_snapshot())
    kwargs.setdefault("audit", AuditLog())
    kwargs.setdefault("role", "analyst")
    kwargs.setdefault("fund_id", "TEST001")
    return AUTH.AgentContext(**kwargs)


def test_agent_catalog_and_chain() -> None:
    catalog = AI.catalog()
    assert catalog["chain"] == list(AI.CHAIN)
    assert set(catalog["agents"]) == {
        "investment_agent",
        "portfolio_agent",
        "risk_agent",
        "valuation_agent",
        "workflow_agent",
    }
    assert catalog["mcp"]["role"] == "Tool Connectivity Layer"
    assert catalog["mcp"]["replaces_riskengine"] is False
    assert set(catalog["mcp"]["capabilities"]) == {
        "Market Data",
        "Portfolio",
        "Risk",
        "Valuation",
        "SQL",
    }
    assert "VaR" in catalog["forbidden_calculations"]


def test_tool_use_and_risk_result_from_engine() -> None:
    result = AI.run("portfolio VaR", agent="risk_agent", context=_ctx())
    assert result["ok"] is True
    assert result["tool"] == "risk.var"
    assert result["calculates"] is False
    payload = result["result"]
    assert payload["kpi"] == "VaR"
    assert payload.get("engine") or payload.get("platform_engine")
    assert "Agent 未自行计算" in result["explanation"] or "RiskEngine" in result["explanation"]


def test_streaming_and_context_events() -> None:
    events = list(AI.stream("price the book", agent="valuation_agent", context=_ctx()))
    names = [item["event"] for item in events]
    for required in (
        "session_start",
        "auth",
        "agent",
        "intent",
        "context",
        "tool_start",
        "result",
        "explanation",
        "audit",
        "session_end",
    ):
        assert required in names
    context_event = next(item for item in events if item["event"] == "context")
    assert context_event["fund_id"] == "TEST001"
    assert events[-1]["ok"] is True


def test_permission_gates_jwt_role_portfolio_api() -> None:
    snapshot = sample_snapshot()
    denied_jwt = AI.run("VaR", agent="risk_agent", context=_ctx(snapshot=snapshot, jwt_valid=False))
    assert denied_jwt["ok"] is False
    assert denied_jwt["error"]["code"] == "JWT"

    denied_role = AI.run("VaR", agent="risk_agent", context=_ctx(snapshot=snapshot, role="intern"))
    assert denied_role["ok"] is False
    assert denied_role["error"]["code"] == "ROLE"

    denied_api = AI.run("VaR", agent="risk_agent", context=_ctx(snapshot=snapshot, api_authorized=False))
    assert denied_api["ok"] is False
    assert denied_api["error"]["code"] == "API"

    denied_fund = AI.run(
        "VaR",
        agent="risk_agent",
        context=_ctx(snapshot=snapshot, portfolio_authorized=False),
    )
    assert denied_fund["ok"] is False
    assert denied_fund["error"]["code"] == "PORTFOLIO"

    denied_perm = AI.run(
        "apply live",
        agent="portfolio_agent",
        context=_ctx(snapshot=snapshot, role="viewer"),
    )
    assert denied_perm["ok"] is False
    assert denied_perm["error"]["code"] == "PERMISSION"


def test_audit_trail() -> None:
    log = AuditLog()
    AI.run("VaR", agent="risk_agent", context=_ctx(audit=log))
    turns = log.entries("AGENT_TURN")
    assert turns
    assert turns[-1]["payload"]["tool"] == "risk.var"
    assert turns[-1]["payload"]["ok"] is True


def test_failure_handling() -> None:
    unknown = AI.run("zzzz-not-an-intent")
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "INTENT"

    missing = AI.run("VaR", agent="risk_agent", context=_ctx(snapshot=None))
    assert missing["ok"] is False
    assert missing["error"]["code"] == "CONTEXT"

    mcp_calc = AI.run(
        "mcp risk",
        agent="risk_agent",
        context=_ctx(),
        extra={"calculate": "VaR"},
    )
    assert mcp_calc["ok"] is False
    assert mcp_calc["error"]["code"] == "MCP_NOT_ENGINE" or mcp_calc["result"]["error"]["code"] == "MCP_NOT_ENGINE"


def test_portfolio_agent_requires_simulation_before_live() -> None:
    ctx = _ctx(role="pm")
    blocked = AI.run("apply live", agent="portfolio_agent", context=ctx)
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "SIMULATION_REQUIRED"

    cloned = AI.run("clone a simulation portfolio", agent="portfolio_agent", context=ctx)
    assert cloned["ok"] is True
    assert cloned["result"]["is_live"] is False
    assert cloned["result"]["sim_id"]

    applied = AI.run("apply live", agent="portfolio_agent", context=ctx)
    assert applied["ok"] is True
    assert applied["result"]["live_modified"] is False
    assert applied["result"]["is_trade_instruction"] is False


def test_mcp_is_connectivity_not_engine() -> None:
    mcp = import_module("7_ai.tools.mcp_layer")
    connected = mcp.connect("Market Data")
    assert connected["layer"] == "Tool Connectivity Layer"
    assert connected["replaces_riskengine"] is False
    assert connected["runtime"] == "4_mcp"
    refused = mcp.refuse_calculate("VaR")
    assert refused["error"]["code"] == "MCP_NOT_ENGINE"


def test_agent_source_does_not_calculate() -> None:
    files: list[Path] = []
    for path in AGENT_CODE_DIRS:
        if path.is_dir():
            files.extend(path.rglob("*.py"))
        elif path.suffix == ".py":
            files.append(path)
    for file in files:
        text = file.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{file} must not import {token}"


def test_legacy_chat_and_mcp_not_removed() -> None:
    assert (ROOT / "aiagent" / "engine" / "runner.py").is_file()
    assert (ROOT / "4_mcp" / "client.py").is_file()
    assert (ROOT / "3_skills" / "skills" / "var-analysis" / "SKILL.md").is_file()
    assert (ROOT / "autorisk").is_dir()


def test_agent_rest_routes() -> None:
    router = import_module("2_processing.api.routers.agents")
    paths = {route.path for route in router.router.routes}
    assert "/catalog" in paths
    assert "/invoke" in paths
    processing = import_module("2_processing.api.main")
    mounted = {getattr(route, "path", "") for route in processing.app.routes}
    assert any("/agents" in path for path in mounted)


def test_workflow_morning_brief() -> None:
    result = AI.run("run morning brief workflow", agent="workflow_agent", context=_ctx())
    assert result["ok"] is True
    assert result["result"]["workflow"] == "morning_brief"
    assert len(result["result"]["steps"]) == 3
