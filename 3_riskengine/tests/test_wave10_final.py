"""Wave 10 final validation: executable institutional chain, engines, API, security, performance.

Results cited by the validation report are written to artefacts/wave10_validation.json.
READY may only be claimed after this module and the rest of the required suites pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import tracemalloc
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .fixtures import SCENARIOS, Shock, RiskFactorType, ShockMode, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTEFACT = ROOT / "artefacts" / "wave10_validation.json"
API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")
HEADERS = {"X-API-Key": API_KEY}

CANONICAL_MASTERS = {
    "Market": "fsi.mktdata_*",
    "Portfolio": "fsi.para_portfolio",
    "Position": "fsi.balance_*",
    "Trade": "fsi.transact_*",
    "Valuation": "fsi.balance_valuation_sheet",
    "NAV": "fsi.balance_portfolio_nav",
    "PnL": "fsi.transact_portfolio_pnl",
    "Risk": "fsi.svc_risk_snapshot",
}

REGRESSION_MODULES = [
    "2_processing.api.routers.data_management",
    "2_processing.api.routers.portfolio_cockpit",
    "2_processing.api.routers.positions",
    "2_processing.api.routers.valuation",
    "2_processing.api.routers.reports",
    "2_processing.api.routers.schedules",
    "2_processing.api.routers.agents",
    "2_processing.api.routers.risk_rules",
    "2_processing.api.routers.review",
    "2_processing.api.routers.op_logs",
    "2_processing.tools.risk_testing",
    "4_mcp.client",
    "autorisk.app.main",
    "aiagent.engine",
    "7_ai.auth",
]


def _write_probe(payload: dict) -> None:
    ARTEFACT.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if ARTEFACT.exists():
        try:
            previous = json.loads(ARTEFACT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
    previous.update(payload)
    ARTEFACT.write_text(json.dumps(previous, indent=2, default=str), encoding="utf-8")


@contextmanager
def processing_client():
    schedules = import_module("2_processing.api.routers.schedules")
    original = schedules.start_scheduler
    schedules.start_scheduler = lambda: None  # type: ignore[method-assign]
    try:
        app = import_module("2_processing.api.main").app
        with TestClient(app) as client:
            yield client
    finally:
        schedules.start_scheduler = original  # type: ignore[method-assign]


def _tables() -> list[str]:
    names: list[str] = []
    schema = ROOT / "1_datastorage" / "postgres" / "schema"
    for path in sorted(schema.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        names.extend(re.findall(r"CREATE TABLE IF NOT EXISTS (fsi\.\w+)", text, re.I))
    return [name.lower() for name in names]


def test_institutional_business_chain() -> None:
    snapshot = sample_snapshot()
    market = import_module("5_integrations.market_data").MarketDataAdapter().pull(
        {"universe": [p.security_code for p in snapshot.positions]}
    )
    assert market.ok is True
    assert market.record.source == "market_data"

    pms = import_module("4_business.trading.lifecycle").current_position(snapshot)
    assert pms["ok"] is True
    assert pms["record"]["source"] == "pms"

    valuation = import_module("3_riskengine.valuation")
    priced = valuation.price(snapshot)
    assert priced.base_pv == pytest.approx(1_000_000.0)

    ir = import_module("4_business.investment_risk.service").compute_kpi_pack(snapshot)
    assert ir["kpis"]["VaR"]["result"]["amount"] is not None
    assert set(ir["domains"]) >= {
        "overview",
        "market_risk",
        "liquidity",
        "counterparty",
        "factor_behavior",
    }

    po = import_module("4_business.portfolio_optimization.service")
    proposal = po.optimize_and_govern(snapshot, "hrp")
    assert proposal["is_trade_instruction"] is False
    assert proposal["gate_status"]["valuation"] is True
    assert proposal["gate_status"]["investment_risk"] is True
    assert proposal["gate_status"]["risk_testing"] is True

    cloned = po.clone_live(snapshot, label="wave10")
    assert cloned["is_live"] is False
    sim_id = cloned["sim_id"]
    stressed = po.stress_simulation(sim_id)
    assert stressed["stress"]["analytic"] == "STRESS"
    compared = po.compare_simulation(sim_id)
    assert "kpi_compare" in compared

    rt = import_module("5_integrations.quant")
    tested = rt.testing.run(snapshot, analytic="SENSITIVITY")
    assert tested["analytic"] == "SENSITIVITY"

    limits = import_module("3_riskengine.limits").evaluate(snapshot)
    assert limits["state"] == "GREEN"

    order = {"security_code": "CASH", "side": "BUY", "amount": 1_000.0, "asset_class": "CASH"}
    pre = import_module("4_business.risk_governance.pre_trade").run_pre_trade(snapshot, order)
    assert pre["decision"] in {"APPROVE", "WARNING"}
    assert pre["is_trade_instruction"] is False

    trading = import_module("4_business.trading.lifecycle")
    accepted = trading.submit_order(snapshot, order)
    assert accepted["status"] == "ACCEPTED_SIM"
    assert accepted["is_trade_instruction"] is False
    post = trading.post_trade(snapshot, order)
    assert post["is_live"] is False

    proposed = import_module("4_business.trading.proposed").apply_proposed_trade(snapshot, order)
    revalued = valuation.price(proposed)
    assert revalued.base_pv > 0
    continuous = import_module("3_riskengine.risk").calculate(
        proposed,
        "sensitivity",
        shocks=(Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),),
    )
    assert continuous["analytic"] == "SENSITIVITY"
    assert continuous["engine_version"]

    _write_probe(
        {
            "chain": {
                "market_data": market.record.record_type,
                "portfolio": snapshot.fund_id,
                "positions": len(snapshot.positions),
                "valuation_pv": priced.base_pv,
                "investment_kpis": len(ir["kpis"]),
                "optimization_method": proposal["method"],
                "simulation_id": sim_id,
                "risk_testing": tested["analytic"],
                "limits": limits["state"],
                "pre_trade": pre["decision"],
                "trading": accepted["status"],
                "continuous_risk": continuous["analytic"],
            }
        }
    )


def test_riskengine_adapters_and_analytics() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    status = engine.adapters_status()
    snapshot = sample_snapshot()
    bound = engine.bind(snapshot)
    shocks = (Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),)

    fp = engine.financepy.initialize()
    rp = engine.riskfolio.initialize()
    ore = engine.ore.initialize()
    assert fp.name == "financepy"
    assert rp.name == "riskfolio"
    assert ore.name == "ore"
    assert engine.financepy.available is True
    assert status["financepy"]["available"] is True

    priced = bound.valuation().price()
    pnl = bound.valuation().pnl(shocks)
    greeks = bound.valuation().greeks(shocks)
    exposure = bound.risk().exposure()
    sensitivity = bound.risk().sensitivity(shocks)
    stress = bound.risk().stress(SCENARIOS["gfc_2008"])
    scenario = bound.risk().scenario(SCENARIOS["fed_hike_75"])
    kpis = bound.risk().kpis()
    limits = bound.limits().evaluate()
    validation = bound.validation().pricing()

    assert priced.base_pv == pytest.approx(1_000_000.0)
    assert pnl["pnl"] < 0
    assert greeks["sensitivities"]
    assert exposure["analytic"] == "EXPOSURE"
    assert sensitivity["analytic"] == "SENSITIVITY"
    assert stress["analytic"] == "STRESS"
    assert scenario["pnl"] < 0
    assert kpis["kpis"]["Liquidity"]["result"]["pct_nav"] == pytest.approx(10.0)
    assert kpis["kpis"]["Counterparty Exposure"]["result"]["counterparty_count"] == 3
    assert limits["state"] == "GREEN"
    assert validation.status == "PASS"

    quant = import_module("5_integrations.quant")
    assert quant.risk.liquidity(snapshot)["kpi"] == "Liquidity"
    assert quant.risk.counterparty(snapshot)["kpi"] == "Counterparty Exposure"

    _write_probe(
        {
            "adapters": {
                "financepy": {
                    "available": bool(status["financepy"]["available"]),
                    "version": status["financepy"].get("version"),
                },
                "riskfolio": {
                    "available": bool(status["riskfolio"]["available"]),
                    "version": status["riskfolio"].get("version"),
                    "error": status["riskfolio"].get("error"),
                },
                "ore": {
                    "available": bool(status["ore"]["available"]),
                    "version": status["ore"].get("version"),
                    "error": status["ore"].get("error"),
                },
            }
        }
    )


def test_three_core_businesses() -> None:
    snapshot = sample_snapshot()
    domains = import_module("4_business.investment_risk.domains")
    pack = import_module("4_business.investment_risk.service").compute_kpi_pack(snapshot)
    assert set(pack["domains"]) == set(domains.MODULE_KPIS)
    for domain in domains.MODULE_KPIS:
        report = domains.analyze_domain(domain, snapshot)
        assert report["engine"] == "ARISK RiskEngine"
        assert report["kpis"]

    po = import_module("4_business.portfolio_optimization.service")
    catalog = po.catalog()
    assert catalog["frontend_routes"] == "/portfolio-opt"
    assert catalog["primary_adapter"] == "riskfolio"
    for method in catalog["methods"]:
        result = po.optimize(po.synthetic_returns(["AAA", "BBB", "CCC", "CASH"]), method)
        assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
        assert result["is_trade_instruction"] is False
    governed = po.optimize_and_govern(snapshot, "construction")
    assert governed["is_trade_instruction"] is False
    assert "ready_for_review" in governed

    rt = import_module("4_business.risk_testing.service")
    caps = rt.capabilities_payload(list(rt.PYTHON_MODULES))
    assert caps["financepy_available"] is True
    assert set(caps["python_modules"]) == set(rt.PYTHON_MODULES)
    engine = import_module("2_processing.tools.risk_testing").ProfessionalRiskEngine(snapshot)
    analytics = import_module("2_processing.tools.risk_testing.analytics")
    assert analytics.sensitivity.run(engine, rt.default_sensitivities())["analytic"] == "SENSITIVITY"
    assert analytics.stress.run(engine, SCENARIOS["gfc_2008"])["analytic"] == "STRESS"
    assert analytics.scenario.run(engine, SCENARIOS["fed_hike_75"])
    assert analytics.krd.run(engine, 1.0)
    assert analytics.xva.run(engine, 0.01, 0.01, 0.4, 0.005, 0.0, 0.0)
    assert analytics.tail_risk.run(engine, (1.0, 2.0, 3.0), snapshot.net_asset * 0.05)
    assert analytics.var_backtest.run(engine, 0.99, 250)
    assert analytics.reverse_stress.run(engine, SCENARIOS["gfc_2008"], 5.0, 5.0)
    assert analytics.pnl_explain.run(engine, snapshot)


def test_master_data_is_not_duplicated() -> None:
    tables = _tables()
    assert len(tables) == len(set(tables)), sorted({name for name in tables if tables.count(name) > 1})
    assert tables.count("fsi.para_portfolio") == 1
    assert tables.count("fsi.balance_portfolio_nav") == 1
    assert tables.count("fsi.balance_valuation_sheet") == 1
    assert tables.count("fsi.transact_portfolio_pnl") == 1
    assert tables.count("fsi.svc_risk_snapshot") == 1
    assert any(name.startswith("fsi.mktdata_") for name in tables)
    assert any(name.startswith("fsi.balance_") for name in tables)
    assert any(name.startswith("fsi.transact_") for name in tables)

    kpis = import_module("3_riskengine.risk.kpis")
    pack = kpis.compute_kpi_pack(sample_snapshot())
    sources = pack["kpis"]["VaR"]["data_quality"]["source_tables"]
    assert sources == ["fsi.balance_*", "fsi.mktdata_*"]
    contracts = (ROOT / "5_integrations" / "contracts.py").read_text(encoding="utf-8")
    assert "not a second" in contracts.lower()
    _write_probe({"data": {"canonical": CANONICAL_MASTERS, "table_count": len(set(tables))}})


def test_existing_capabilities_still_import() -> None:
    for name in REGRESSION_MODULES:
        assert import_module(name) is not None
    assert (ROOT / "2_processing" / "tools" / "mmf" / "run_report.py").is_file()
    mcp_layer = import_module("7_ai.tools.mcp_layer")
    denied = mcp_layer.connect("Risk", arguments={"calculate": "VaR"})
    assert denied["ok"] is False
    assert denied["error"]["code"] == "MCP_NOT_ENGINE"
    processing = import_module("2_processing.api.main")
    paths = {getattr(route, "path", "") for route in processing.app.routes}
    for prefix in (
        "/positions",
        "/data-management",
        "/valuation",
        "/portfolio-cockpit",
        "/portfolio-opt",
        "/risk-testing",
        "/quant",
        "/agents",
        "/risk",
        "/risk-rules",
        "/investment",
        "/reports",
        "/schedules",
        "/review",
        "/op-logs",
    ):
        assert any(prefix in path for path in paths), prefix


def test_third_party_versions_and_patch_log() -> None:
    vendor = import_module("3_riskengine.adapters.vendor")
    financepy, _ = vendor.probe_module("financepy")
    riskfolio, _ = vendor.probe_module("riskfolio")
    quantlib, _ = vendor.probe_module("QuantLib")
    patches = (ROOT / "docs" / "third_party_patches.md").read_text(encoding="utf-8")
    assert "当前 **没有** 对 FinancePy、Riskfolio-Lib、ORE 源码的修改" in patches
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "FinancePy/" in gitignore
    assert "Riskfolio-Lib/" in gitignore
    assert "ORE/" in gitignore
    assert financepy.available is True
    assert financepy.version
    _write_probe(
        {
            "third_party": {
                "financepy": {
                    "available": financepy.available,
                    "version": financepy.version,
                    "path": financepy.module_path,
                },
                "riskfolio": {
                    "available": riskfolio.available,
                    "version": riskfolio.version,
                    "error": riskfolio.error,
                },
                "QuantLib": {
                    "available": quantlib.available,
                    "version": quantlib.version,
                    "error": quantlib.error,
                },
                "patches": "none",
            }
        }
    )


def test_processing_api_auth_and_new_contracts() -> None:
    with processing_client() as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        denied = client.get("/quant/catalog")
        assert denied.status_code == 403

        catalog = client.get("/quant/catalog", headers=HEADERS)
        assert catalog.status_code == 200
        assert set(catalog.json()["channels"]) == {"Python", "Jupyter", "CLI", "REST"}

        var = client.post(
            "/quant/risk/var",
            headers=HEADERS,
            json={"holdings": {"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1}},
        )
        assert var.status_code == 200
        assert var.json()["kpi"] == "VaR"

        priced = client.post("/quant/valuation/price", headers=HEADERS, json={})
        assert priced.status_code == 200
        assert priced.json()["base_pv"] > 0

        tested = client.post("/quant/testing/run", headers=HEADERS, json={"analytic": "SENSITIVITY"})
        assert tested.status_code == 200

        agents = client.get("/agents/catalog", headers=HEADERS)
        assert agents.status_code == 200
        invoked = client.post(
            "/agents/invoke",
            headers=HEADERS,
            json={"message": "portfolio VaR", "fund_id": "TEST001"},
        )
        assert invoked.status_code == 200
        assert invoked.json()["ok"] is True

        limits = client.get("/risk/limits/catalog", headers=HEADERS)
        assert limits.status_code == 200
        pre = client.post(
            "/risk/pre-trade",
            headers=HEADERS,
            json={
                "security_code": "CASH",
                "amount": 1000,
                "asset_class": "CASH",
                "holdings": {"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1},
            },
        )
        assert pre.status_code == 200
        assert pre.json()["decision"] in {"APPROVE", "WARNING", "REJECT"}

        opt = client.get("/portfolio-opt/catalog", headers=HEADERS)
        assert opt.status_code == 200
        ir = client.get("/investment/kpi-catalog", headers=HEADERS)
        assert ir.status_code == 200
        rt = client.get("/risk-testing/catalog", headers=HEADERS)
        assert rt.status_code == 200

        unauthorized_agent = client.post(
            "/agents/invoke",
            headers=HEADERS,
            json={
                "message": "apply live weights",
                "role": "viewer",
                "apply_live": True,
                "fund_id": "TEST001",
            },
        )
        assert unauthorized_agent.status_code == 403


def test_agent_security_gates() -> None:
    auth = import_module("7_ai.auth")
    ctx = auth.AgentContext(jwt_present=False, jwt_valid=False)
    with pytest.raises(auth.AgentAuthError) as exc:
        auth.guard_identity(ctx)
    assert exc.value.code == "JWT"
    missing = auth.AgentContext(jwt_present=True, jwt_valid=True, role="viewer")
    with pytest.raises(auth.AgentAuthError):
        auth.guard_tool(missing, "portfolio.apply_live")
    forbidden_fund = auth.AgentContext(fund_id="OTHER", authorized_funds=frozenset({"TEST001"}))
    with pytest.raises(auth.AgentAuthError) as portfolio:
        auth.guard_portfolio(forbidden_fund, "OTHER")
    assert portfolio.value.code == "PORTFOLIO"


def test_frontend_routes_permissions_and_release_stages() -> None:
    nav = (ROOT / "frontend" / "src" / "platform" / "nav.ts").read_text(encoding="utf-8")
    sidebar = (ROOT / "frontend" / "src" / "components" / "Sidebar" / "AppSidebar.tsx").read_text(encoding="utf-8")
    routes = ROOT / "frontend" / "src" / "routes" / "_layout"
    required = [
        "investment-risk.overview.tsx",
        "portfolio-opt.tsx",
        "risk-testing.sensitivity.tsx",
        "data-management.tsx",
        "portfolio-cockpit.tsx",
        "positions.tsx",
        "valuation.tsx",
        "reports.tsx",
        "schedules.tsx",
        "autorisk.tsx",
        "chat.tsx",
        "compliance.tsx",
        "risk-rules.tsx",
    ]
    for name in required:
        assert (routes / name).is_file(), name
    assert 'id: "investment-overview"' in nav
    assert "/portfolio-opt#construction" in nav
    assert "/risk-testing/sensitivity" in nav
    assert 'menuStages[path] !== "HIDDEN"' in sidebar
    assert 'itemStage === "BETA"' in sidebar
    spec = (ROOT / "frontend" / "tests" / "menu-architecture.spec.ts").read_text(encoding="utf-8")
    assert "deep links" in spec.lower()
    assert "menuStages" in spec
    assert "HIDDEN" in spec
    assert "BETA" in spec


def test_performance_probe() -> None:
    snapshot = sample_snapshot()
    valuation = import_module("3_riskengine.valuation")
    risk = import_module("3_riskengine.risk")
    po = import_module("4_business.portfolio_optimization.service")
    shocks = (Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),)

    tracemalloc.start()
    t0 = time.perf_counter()
    valuation.price(snapshot)
    valuation_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    risk.calculate(snapshot, "sensitivity", shocks=shocks)
    risk_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    risk.stress(snapshot, SCENARIOS["gfc_2008"])
    stress_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    po.optimize_and_govern(snapshot, "hrp")
    opt_ms = (time.perf_counter() - t0) * 1000
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    with processing_client() as client:
        t0 = time.perf_counter()
        response = client.get("/health")
        health_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        catalog = client.get("/quant/catalog", headers=HEADERS)
        catalog_ms = (time.perf_counter() - t0) * 1000
    assert response.status_code == 200
    assert catalog.status_code == 200

    db_ms = None
    db_error = None
    try:
        from sqlalchemy import create_engine, text

        url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fsi_risk")
        sync = url.replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(sync, pool_pre_ping=True)
        t0 = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ms = (time.perf_counter() - t0) * 1000
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 — probe must record env failure
        db_error = f"{type(exc).__name__}: {exc}"

    redis_ok = False
    redis_error = None
    try:
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client_redis = redis.Redis.from_url(redis_url, socket_connect_timeout=1)
        redis_ok = bool(client_redis.ping())
        client_redis.close()
    except Exception as exc:  # noqa: BLE001
        redis_error = f"{type(exc).__name__}: {exc}"

    schedules = import_module("2_processing.api.routers.schedules")
    schedules.start_scheduler()
    assert schedules._sched_started is True
    assert schedules._sched_thread is not None
    assert schedules._sched_thread.is_alive()

    timings = {
        "valuation_ms": round(valuation_ms, 3),
        "risk_ms": round(risk_ms, 3),
        "stress_ms": round(stress_ms, 3),
        "optimization_ms": round(opt_ms, 3),
        "api_health_ms": round(health_ms, 3),
        "api_quant_catalog_ms": round(catalog_ms, 3),
        "database_ms": None if db_ms is None else round(db_ms, 3),
        "database_error": db_error,
        "redis_ok": redis_ok,
        "redis_error": redis_error,
        "memory_peak_kib": round(peak / 1024, 1),
        "memory_current_kib": round(current / 1024, 1),
        "scheduler_alive": True,
    }
    _write_probe({"performance": timings})
    assert valuation_ms < 5_000
    assert risk_ms < 5_000
    assert stress_ms < 5_000
    assert opt_ms < 15_000
    assert health_ms < 1_000
    assert catalog_ms < 5_000
