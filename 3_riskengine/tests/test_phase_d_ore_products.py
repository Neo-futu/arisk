"""Phase D: ORE trade / complex products on the unified valuation path."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import Shock, RiskFactorType, ShockMode, sample_otc_snapshot, sample_snapshot


EXPECTED_KINDS = [
    "FX",
    "FX_FORWARD",
    "FX_OPTION",
    "FUTURE",
    "OPTION",
    "IRS",
    "SWAPTION",
    "CDS",
]


def test_otc_products_assemble_and_resolve_to_ore() -> None:
    products = import_module("3_riskengine.products")
    engine = import_module("3_riskengine").RiskEngine()
    snapshot = sample_otc_snapshot()
    lines = products.products_from_snapshot(snapshot, view="LOOK_THROUGH")
    assert [item.kind.value for item in lines] == EXPECTED_KINDS
    for item in lines:
        ref = engine.resolve(item, "PRICE")
        assert ref.adapter == "ore"
    trades = engine.bind(snapshot).trades()
    assert [trade.instrument.product_kind.value for trade in trades] == EXPECTED_KINDS
    mapping = engine.ore.map_snapshot(snapshot)
    assert mapping["ore_app"] is False
    types = {row["id"]: row["type"] for row in mapping["trades"]}
    assert types["IRS5Y"] == "Swap"
    assert types["SWPT"] == "Swaption"
    assert types["CDS5Y"] == "CreditDefaultSwap"
    assert types["FXFWD"] == "FxForward"
    assert types["FXOPT"] == "FxOption"


def test_otc_unified_valuation_zero_shock_is_book_value() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_otc_snapshot())
    priced = bound.valuation().price()
    assert priced.base_pv == pytest.approx(300_000.0, abs=1e-4)
    by_kind = {row["asset_class"]: row for row in priced.trade_values}
    assert by_kind["IRS"]["engine"] == "ore"
    assert by_kind["CDS"]["engine"] == "ore"
    assert by_kind["FX_OPTION"]["engine"] == "ore"
    assert by_kind["SWAPTION"]["engine"] == "ore"
    flows = bound.valuation().cashflows()
    assert len(flows["products"]) == 8
    assert all(item["engine"] == "ore" for item in flows["products"])


def test_otc_rate_vol_fx_and_credit_shocks_move_npv() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_otc_snapshot())
    rate = bound.valuation().revalue((Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),))
    fx = bound.valuation().revalue((Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE),))
    vol = bound.valuation().revalue((Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE),))
    spread = bound.valuation().revalue((Shock(RiskFactorType.CREDIT_SPREAD, 0.0005, ShockMode.ABSOLUTE),))
    equity = bound.valuation().revalue((Shock(RiskFactorType.EQUITY, 0.05, ShockMode.RELATIVE),))
    assert rate.pnl != 0.0
    assert fx.pnl != 0.0
    assert vol.pnl != 0.0
    assert spread.pnl != 0.0
    assert equity.pnl != 0.0
    irs = next(row for row in rate.trade_values if row["asset_class"] == "IRS")
    assert irs["engine"] == "ore"
    assert irs["pnl"] != 0.0
    swpt = next(row for row in vol.trade_values if row["asset_class"] == "SWAPTION")
    assert swpt["pnl"] != 0.0
    cds = next(row for row in spread.trade_values if row["asset_class"] == "CDS")
    assert cds["pnl"] != 0.0


def test_ore_american_fx_option_still_matches_reference() -> None:
    from datetime import date

    ore = import_module("3_riskengine.adapters.ore").OREAdapter()
    american = ore.price_american_fx_future_option(
        future_price=1.08,
        strike=1.08,
        risk_free_rate=0.045,
        volatility=0.10,
        as_of=date(2026, 9, 10),
        maturity=date(2027, 3, 10),
    )
    assert american["library"] == "ORE"
    assert abs(american["npv"] - 0.029758) < 1e-5
    assert "OREApp" not in str(american)


def test_existing_cash_book_valuation_unchanged() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    priced = bound.valuation().price()
    assert priced.base_pv == pytest.approx(1_000_000.0)
    mapping = bound.engine.ore.map_snapshot(sample_snapshot())
    assert {item["id"] for item in mapping["trades"]} == {"BOND5Y", "US_EQ", "CASH"}
    assert mapping["ore_app"] is False
