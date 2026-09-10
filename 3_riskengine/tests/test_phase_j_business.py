"""Phase J: three business domains call RiskEngine, not vendor libraries."""
from __future__ import annotations

from datetime import date
from importlib import import_module

from .fixtures import sample_snapshot


def test_investment_risk_liquidity_and_counterparty_use_engine() -> None:
    snapshot = sample_snapshot()
    domains = import_module("4_business.investment_risk.domains")
    liquidity = domains.analyze_domain("liquidity", snapshot)
    counterparty = domains.analyze_domain("counterparty", snapshot)
    assert liquidity["engine"] == "ARISK RiskEngine"
    assert liquidity["liquidity"]["analytic"] == "LIQUIDITY"
    assert counterparty["counterparty"]["analytic"] == "COUNTERPARTY"
    assert counterparty["counterparty"]["ore_app"] is False


def test_risk_testing_run_uses_riskengine() -> None:
    snapshot = sample_snapshot()
    rt = import_module("4_business.risk_testing.service")
    sensitivity = rt.run(snapshot, "SENSITIVITY")
    krd = rt.run(snapshot, "KRD")
    xva = rt.run(snapshot, "XVA")
    assert sensitivity["analytic"] == "SENSITIVITY"
    assert krd["analytic"] == "KRD"
    assert xva["analytic"] == "XVA"
    assert xva["ore_app"] is False
    assert sensitivity["engine"] == "ARISK RiskEngine" or sensitivity.get("riskengine") == "ARISK RiskEngine"


def test_quant_and_optimization_stay_on_riskengine() -> None:
    snapshot = sample_snapshot()
    quant = import_module("5_integrations.quant")
    tested = quant.testing.run(snapshot, analytic="XVA")
    priced = quant.valuation.price(snapshot)
    po = import_module("4_business.portfolio_optimization.service")
    review = po.optimize_and_govern(snapshot, "hrp")
    assert tested["analytic"] == "XVA"
    assert priced["base_pv"] == snapshot.net_asset
    assert review["is_trade_instruction"] is False
    assert review["limits"]["engine"] == "ARISK RiskEngine"


def test_pnl_explain_on_business_run() -> None:
    rt = import_module("4_business.risk_testing.service")
    current = sample_snapshot(date(2026, 9, 1), equity_value=300_000.0)
    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    explain = rt.run(current, "PNL_EXPLAIN", previous=previous)
    assert explain["analytic"] == "PNL_EXPLAIN"
