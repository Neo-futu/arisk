"""Phase C: unified valuation price / revalue / greeks / cashflows / pnl."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import Shock, RiskFactorType, ShockMode, sample_mmf_snapshot, sample_snapshot


def test_valuation_price_revalue_greeks_cashflows_pnl() -> None:
    valuation = import_module("3_riskengine.valuation")
    snapshot = sample_snapshot()
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    priced = valuation.price(snapshot)
    revalued = valuation.revalue(snapshot, (shock,))
    greeks = valuation.greeks(snapshot, (shock,))
    flows = valuation.cashflows(snapshot)
    pnl = valuation.pnl(snapshot, (shock,))
    kinds = {row["asset_class"] for row in priced.trade_values}
    assert priced.base_pv == pytest.approx(1_000_000.0)
    assert kinds == {"BOND", "EQUITY", "CASH"}
    assert revalued.pnl < 0.0
    assert greeks["sensitivities"][0]["delta"] != 0.0
    assert flows["analytic"] == "CASHFLOW"
    assert len(flows["products"]) == 3
    bond_flows = next(item for item in flows["products"] if item["asset_class"] == "BOND")
    assert {flow["type"] for flow in bond_flows["flows"]} == {"coupon", "redemption"}
    assert bond_flows["engine"] == "financepy"
    equity_row = next(item for item in priced.trade_values if item["asset_class"] == "EQUITY")
    assert equity_row["engine"] == "financepy"
    assert pnl["pnl"] == pytest.approx(revalued.pnl)


def test_valuation_matches_kernel_for_rate_shock() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    via_products = engine.valuation().revalue((shock,))
    via_kernel = engine.kernel().value((shock,))
    assert via_products.base_pv == pytest.approx(via_kernel["base_pv"], abs=1e-4)
    assert via_products.shocked_pv == pytest.approx(via_kernel["shocked_pv"], abs=1e-4)
    assert via_products.pnl == pytest.approx(via_kernel["pnl"], abs=1e-4)


def test_mmf_book_product_and_look_through_valuation() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_mmf_snapshot())
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    lines = engine.valuation().price(view="LOOK_THROUGH")
    book = engine.valuation().price(view="PRODUCT")
    kinds = [row["asset_class"] for row in lines.trade_values]
    assert sorted(kinds) == ["BOND", "CASH", "CD", "DEPOSIT"]
    assert len(book.trade_values) == 1
    assert book.trade_values[0]["asset_class"] == "MMF"
    assert book.trade_values[0]["engine"] == "riskengine"
    assert lines.base_pv == pytest.approx(1_000_000.0)
    assert book.base_pv == pytest.approx(1_000_000.0)
    revalued = engine.valuation().revalue((shock,), view="PRODUCT")
    assert revalued.pnl < 0.0
    flows = engine.valuation().cashflows(view="PRODUCT")
    assert flows["products"][0]["flows"][0]["type"] == "nav"
    through = engine.valuation().cashflows(view="LOOK_THROUGH")
    assert len(through["products"]) == 4
    kernel = engine.kernel().value((shock,))
    look = engine.valuation().revalue((shock,), view="LOOK_THROUGH")
    assert look.pnl == pytest.approx(kernel["pnl"], abs=1e-4)


def test_equity_relative_shock_on_unified_valuation() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    shock = Shock(RiskFactorType.EQUITY, -0.10, ShockMode.RELATIVE)
    revalued = engine.valuation().revalue((shock,))
    equity = next(item for item in revalued.trade_values if item["asset_class"] == "EQUITY")
    assert equity["shocked_pv"] == pytest.approx(270_000.0)
    assert revalued.pnl == pytest.approx(-30_000.0)
