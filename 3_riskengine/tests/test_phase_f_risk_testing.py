"""Phase F: Risk Testing analytics on the unified RiskEngine path."""
from __future__ import annotations

from datetime import date
from importlib import import_module

import pytest

from .fixtures import SCENARIOS, Shock, RiskFactorType, ShockMode, sample_snapshot


def _bound():
    return import_module("3_riskengine").RiskEngine().bind(sample_snapshot())


def test_resolve_routes_testing_analytics() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    contracts = import_module("3_riskengine.core.contracts")
    assert engine.resolve("BOND", "SENSITIVITY").adapter == "financepy"
    assert engine.resolve("BOND", "STRESS").adapter == "riskengine"
    assert engine.resolve("IRS", "SCENARIO").adapter == "riskengine"
    assert engine.resolve("EQUITY", "TAIL_RISK").adapter == "riskfolio"
    assert engine.resolve("BOND", "KRD").adapter == "financepy"
    assert engine.resolve("IRS", contracts.AnalyticKind.XVA).adapter == "ore"
    assert engine.resolve("EQUITY", "VAR_BACKTEST").adapter == "riskfolio"


def test_sensitivity_stress_scenario_use_product_revalue() -> None:
    bound = _bound()
    shock = Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE)
    greeks = bound.risk().sensitivity((shock,))
    crisis = bound.stress().run(SCENARIOS["gfc_2008"])
    hike = bound.scenario().named("fed_hike_75")
    assert greeks["analytic"] == "SENSITIVITY"
    assert greeks["sensitivities"][0]["delta"] != 0.0
    assert crisis["analytic"] == "STRESS"
    assert crisis["pnl"] < 0.0
    assert crisis["ore_app"] is False
    assert "EQUITY" in crisis["by_asset_class"]
    assert hike["analytic"] == "SCENARIO"
    assert hike["pnl"] < 0.0
    assert hike["engine"] == "ARISK RiskEngine"


def test_reverse_stress_tail_krd_and_backtests() -> None:
    bound = _bound()
    reverse = bound.stress().reverse(SCENARIOS["gfc_2008"], 5.0, 10.0)
    tail = bound.risk().tail_risk((3.0, 4.0, 5.0), 80_000.0)
    krd = bound.risk().krd(1.0)
    hist = bound.risk().historical_backtest()
    var_bt = bound.risk().var_backtest(0.99, 60)
    assert reverse["analytic"] == "REVERSE_STRESS"
    assert reverse["breach_reached"] is True
    assert -reverse["pnl"] == pytest.approx(reverse["target_loss_amount"], rel=1e-4)
    losses = [item["loss_amount"] for item in tail["tail_scenarios"]]
    assert losses == sorted(losses)
    assert tail["expected_shortfall_99_amount"] >= tail["historical_var_99_amount"] - 1e-9
    bucket = next(item for item in krd["buckets"] if item["tenor"] == "5Y")
    assert bucket["pv01"] < 0.0
    assert hist["analytic"] == "HISTORICAL_BACKTEST"
    assert hist["observation_count"] >= 2
    assert hist["max_drawdown_pct"] < 0
    assert var_bt["status"] == "OK"
    assert var_bt["observations"] == 240
    assert var_bt["traffic_light"] in {"GREEN", "YELLOW", "RED"}


def test_pnl_explain_xva_and_governance() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    bound = engine.bind(sample_snapshot(date(2026, 9, 1), equity_value=300_000.0))
    explain = bound.pnl().explain(previous)
    xva = bound.counterparty().xva()
    review = bound.governance().review()
    totals = explain["totals"]
    explained = (
        totals["carry"]
        + totals["rates"]
        + totals["fx"]
        + totals["position"]
        + totals["residual"]
    )
    assert explain["analytic"] == "PNL_EXPLAIN"
    assert explained == pytest.approx(totals["total"])
    assert "credit" in totals and "equity" in totals
    assert xva["analytic"] == "XVA"
    assert xva["ore_app"] is False
    assert xva["cva"] >= 0.0
    assert len(xva["exposure_profile"]) == 20
    assert set(xva["trades"]) == {"BOND5Y", "US_EQ", "CASH"}
    assert review["is_trade_instruction"] is False
    assert review["passed"] is True
