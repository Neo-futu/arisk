"""Phase E: portfolio / fund aggregation with Riskfolio VaR, CVaR, RC and optimize."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import sample_mmf_snapshot, sample_otc_snapshot, sample_snapshot


def test_cash_book_aggregates_to_nav() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    book = bound.portfolio().aggregate()
    assert book["base_pv"] == pytest.approx(1_000_000.0)
    assert book["gross"] == pytest.approx(1_000_000.0)
    assert set(book["by_asset_class"]) == {"BOND", "EQUITY", "CASH"}
    assert abs(sum(row["weight"] for row in book["positions"]) - 1.0) < 1e-9
    exposure = bound.risk().exposure()
    assert exposure["analytic"] == "EXPOSURE"
    assert exposure["by_asset_class"]["BOND"]["base_pv"] == pytest.approx(600_000.0)


def test_portfolio_risk_and_fund_risk_share_nav_var() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    portfolio = bound.portfolio().risk()
    fund = bound.portfolio().fund_risk()
    assert portfolio["scope"] == "PORTFOLIO"
    assert fund["scope"] == "FUND"
    assert portfolio["base_pv"] == pytest.approx(fund["base_pv"])
    var = bound.risk().var()
    cvar = bound.risk().cvar()
    assert var["analytic"] == "VAR"
    assert cvar["analytic"] == "CVAR"
    assert var["var_amount"] is not None
    assert cvar["cvar_amount"] >= var["var_amount"] - 1e-9
    assert var["engine"] in {"riskfolio", "riskengine_numpy", "riskengine_numpy_fallback"}
    assert fund["volatility_ann"] > 0
    assert fund["max_drawdown"] < 0


def test_mmf_fund_is_one_product_portfolio_is_look_through() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_mmf_snapshot())
    fund = bound.risk().fund()
    portfolio = bound.risk().portfolio()
    assert fund["product_count"] == 1
    assert fund["products"][0]["asset_class"] == "MMF"
    assert fund["base_pv"] == pytest.approx(1_000_000.0)
    assert portfolio["position_count"] == 4
    assert set(portfolio["by_asset_class"]) == {"BOND", "CD", "DEPOSIT", "CASH"}
    assert portfolio["base_pv"] == pytest.approx(1_000_000.0)


def test_otc_products_roll_into_portfolio_book() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_otc_snapshot())
    book = bound.portfolio().aggregate()
    assert book["base_pv"] == pytest.approx(300_000.0)
    assert set(book["by_asset_class"]) >= {"IRS", "SWAPTION", "CDS", "FX_OPTION", "FX_FORWARD"}
    assert book["by_engine"]["ore"]["base_pv"] == pytest.approx(300_000.0)


def test_risk_contribution_sums_to_one() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    contrib = bound.risk().contribution()
    statistical = contrib["statistical"]
    assert statistical
    assert abs(sum(statistical.values()) - 1.0) < 1e-6
    assert abs(sum(contrib["by_asset_class"].values()) - 1.0) < 1e-6
    assert contrib["factor_pnl"]["by_asset_class"]
    assert contrib["weights"]["BOND5Y"] == pytest.approx(0.6)


def test_optimize_hrp_is_a_proposal() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    result = bound.risk().optimize("hrp")
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6
    assert result["is_trade_instruction"] is False
    assert result["status"] in {"PROPOSAL", "INSUFFICIENT_DATA"}
    assert result["engine"] in {"riskfolio", "riskengine_fallback"}
    assert set(result["risk_contribution"]) == set(result["weights"])
    assert result["current_weights"]["BOND5Y"] == pytest.approx(0.6)
