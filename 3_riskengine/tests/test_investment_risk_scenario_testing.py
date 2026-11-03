"""风险情景分析：十个子菜单业务模块经 RiskEngine。"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import SCENARIOS, Shock, RiskFactorType, ShockMode, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "risk-testing" / "RiskTestingPage.tsx"
NAV = ROOT / "frontend" / "src" / "platform" / "nav.ts"


def test_frontend_risk_testing_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "SENSITIVITY",
        "STRESS",
        "SCENARIO",
        "REVERSE_STRESS",
        "TAIL_RISK",
        "KRD",
        "PNL_EXPLAIN",
        "HISTORICAL_BACKTEST",
        "VAR_BACKTEST",
        "XVA",
        "结构化风险结果",
        "运行测试",
    ):
        assert token in text, token
    nav = NAV.read_text(encoding="utf-8")
    assert "/risk-testing/sensitivity" in nav
    assert "/risk-testing/var-backtest" in nav


def test_ten_business_modules_catalog() -> None:
    st = import_module("3_riskengine.risk.scenario_testing")
    assert len(st.BUSINESS_MODULES) == 10
    catalog = st.catalog()
    assert {row["analytic"] for row in catalog} == set(st.BUSINESS_MODULES)
    for row in catalog:
        assert row["path"].startswith("/risk-testing/")
        assert row["formula"]
        assert row["time_semantics"] in {"POINT_IN_TIME", "DATE_RANGE"}


def test_sensitivity_module_pack() -> None:
    st = import_module("3_riskengine.risk.scenario_testing")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .risk_testing("SENSITIVITY")
    )
    check = st.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["analytic"] == "SENSITIVITY"
    assert pack["page"] == "/risk-testing/sensitivity"
    assert pack["modules"]["kpi_cards"]["rows"]
    assert pack["modules"]["result_table"]["rows"]
    assert pack["modules"]["methodology"]["formula"]
    assert pack["implementation"]["business_module"].startswith("3_riskengine.risk.scenario_testing")
    assert pack["sensitivities"]


def test_all_analytics_smoke() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    snap = sample_snapshot()
    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    bound = engine.bind(snap)
    st = import_module("3_riskengine.risk.scenario_testing")

    cases = [
        ("SENSITIVITY", {}),
        ("STRESS", {"scenario": SCENARIOS["gfc_2008"]}),
        ("SCENARIO", {"scenario_id": "fed_hike_75"}),
        ("REVERSE_STRESS", {"scenario": SCENARIOS["gfc_2008"], "target_loss_pct_nav": 5.0, "max_scale": 10.0}),
        ("TAIL_RISK", {"sigma_levels": (3.0, 4.0, 5.0), "capital_buffer": 80_000.0}),
        ("KRD", {"bump_bps": 1.0}),
        ("PNL_EXPLAIN", {"previous": previous}),
        ("HISTORICAL_BACKTEST", {}),
        ("VAR_BACKTEST", {"confidence": 0.99, "window": 60}),
        ("XVA", {}),
    ]
    for analytic, kwargs in cases:
        pack = bound.risk().risk_testing(analytic, **kwargs)
        assert pack["analytic"] == analytic, analytic
        assert st.verify_business_modules(pack)["passed"], (analytic, st.verify_business_modules(pack))
        assert pack["modules"]["parameters"]["analytic"] == analytic


def test_custom_shock_and_default_shocks() -> None:
    st = import_module("3_riskengine.risk.scenario_testing")
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="利率 +1bp")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .risk_testing("SENSITIVITY", shocks=(shock,))
    )
    assert len(pack["sensitivities"]) == 1
    assert pack["sensitivities"][0]["delta"] != 0.0
    assert len(st.default_shocks()) == 5


def test_business_service_run_uses_engine_pack() -> None:
    service = import_module("4_business.risk_testing.service")
    report = service.run(sample_snapshot(), "SENSITIVITY")
    assert report["analytic"] == "SENSITIVITY"
    assert "modules" in report
    assert report["implementation"]["business_module"].startswith("3_riskengine.risk.scenario_testing")
    caps = service.capabilities_payload(list(service.PYTHON_MODULES))
    assert caps["engine"] == "ARISK RiskEngine" or "RiskEngine" in str(caps["engine"])
    assert caps["python_modules"]["SENSITIVITY"].startswith("3_riskengine")
