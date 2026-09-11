"""Phase B: Equity / Bond / MMF / Deposit / CD as first-class products."""
from __future__ import annotations

from importlib import import_module

from .fixtures import Shock, RiskFactorType, ShockMode, sample_mmf_snapshot, sample_snapshot


def test_product_view_maps_equity_bond_cash() -> None:
    products = import_module("3_riskengine.products")
    classify = import_module("3_riskengine.instruments")
    snapshot = sample_snapshot()
    lines = products.products_from_snapshot(snapshot, view=products.ViewMode.PRODUCT)
    kinds = [item.kind.value for item in lines]
    assert kinds == ["BOND", "EQUITY", "CASH"]
    assert classify.product_kind_of(snapshot.positions[0]).value == "BOND"
    assert classify.is_equity_like(snapshot.positions[1])
    assert not classify.is_equity_like(snapshot.positions[0])
    through = products.products_from_snapshot(snapshot, view=products.ViewMode.LOOK_THROUGH)
    assert [item.kind.value for item in through] == kinds


def test_mmf_is_first_class_product_and_look_through() -> None:
    products = import_module("3_riskengine.products")
    models = import_module("3_riskengine.models")
    snapshot = sample_mmf_snapshot()
    books = products.products_from_snapshot(snapshot, view="PRODUCT")
    assert len(books) == 1
    mmf = books[0]
    assert isinstance(mmf, products.MoneyMarketFund)
    assert mmf.kind.value == "MMF"
    assert [item.kind.value for item in mmf.look_through()] == ["BOND", "CD", "DEPOSIT", "CASH"]
    lines = products.products_from_snapshot(snapshot, view="LOOK_THROUGH")
    assert [item.kind.value for item in lines] == ["BOND", "CD", "DEPOSIT", "CASH"]
    engine = import_module("3_riskengine").RiskEngine()
    market = engine.bind(snapshot).market()
    nav_view = mmf.value(market, models.MMF_NAV)
    through = mmf.value(market, models.MMF_LOOK_THROUGH)
    assert through == nav_view
    assert abs(through - snapshot.net_asset) < 1e-6
    assert 0.0 < mmf.wam_days(snapshot.as_of_date) <= mmf.wal_days(snapshot.as_of_date)


def test_bond_deposit_cd_use_financepy_market_identity() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    snapshot = sample_mmf_snapshot()
    bound = engine.bind(snapshot)
    market = bound.market()
    assert market.curves["engine"] == "FinancePy"
    by_kind = {item.kind.value: item for item in bound.products(view="LOOK_THROUGH")}
    assert abs(by_kind["BOND"].value(market) - 400_000.0) < 1e-4
    assert abs(by_kind["CD"].value(market) - 250_000.0) < 1e-4
    assert abs(by_kind["DEPOSIT"].value(market) - 250_000.0) < 1e-4
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    pnl = by_kind["BOND"].sensitivity(market, (shock,))["pnl"]
    assert pnl < 0.0
    mmf = bound.products(view="PRODUCT")[0]
    pack = mmf.sensitivity(market, (shock,))
    assert pack["view"] == "LOOK_THROUGH"
    assert pack["pnl"] < 0.0


def test_equity_value_and_relative_shock() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    snapshot = sample_snapshot()
    bound = engine.bind(snapshot)
    market = bound.market()
    equity = next(item for item in bound.products() if item.kind.value == "EQUITY")
    assert equity.value(market) == 300_000.0
    shock = Shock(RiskFactorType.EQUITY, -0.10, ShockMode.RELATIVE)
    pack = equity.sensitivity(market, (shock,))
    assert pack["shocked_pv"] == 270_000.0


def test_fund_line_with_mmf_type_is_mmf_product() -> None:
    products = import_module("3_riskengine.products")
    models = import_module("2_processing.tools.risk_testing.models")
    holding = models.Position(
        security_code="EXTMMF",
        security_name="External MMF",
        asset_class="FUND",
        currency="HKD",
        market_value=50_000.0,
        market_value_base=50_000.0,
        metadata={"issuer": "MMF", "fund_type": "MMF"},
    )
    product = products.product_from_holding(holding)
    assert isinstance(product, products.MoneyMarketFund)
    assert product.kind.value == "MMF"
