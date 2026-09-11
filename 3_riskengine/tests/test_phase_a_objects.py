"""Phase A: canonical RiskEngine objects, routing and lineage."""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("import financepy", "import riskfolio", "import QuantLib", "import ORE")


def test_phase_a_objects_compose_without_second_master() -> None:
    contracts = import_module("3_riskengine.core.contracts")
    instrument = contracts.Instrument(
        instrument_id="BOND5Y",
        asset_class="BOND",
        currency="HKD",
        name="Five Year Bond",
        product_kind=contracts.ProductKind.BOND,
        maturity_date=date(2031, 8, 31),
    )
    product = contracts.Product(kind=contracts.ProductKind.BOND, instrument=instrument)
    model = contracts.Model(name="flat_discount", family="fixed_income")
    market = contracts.Market(valuation_date=date(2026, 9, 1), prices={"BOND5Y": 100.0})
    trade = contracts.Trade(
        trade_id="T1",
        instrument=instrument,
        counterparty="ISSUER",
        portfolio_id="TEST001",
        quantity=600_000.0,
    )
    position = contracts.Position(
        instrument=instrument,
        security_code="BOND5Y",
        quantity_value=600_000.0,
        market_value=600_000.0,
        market_value_base=600_000.0,
        trade_id="T1",
        portfolio_id="TEST001",
    )
    portfolio = contracts.Portfolio(
        portfolio_id="TEST001",
        as_of_date=date(2026, 9, 1),
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[position],
        kind=contracts.PortfolioKind.LIVE,
        trades=[trade],
    )
    snapshot = contracts.MarketSnapshot(
        as_of_date=date(2026, 9, 1),
        reporting_currency="HKD",
        market=market,
    )
    factor = contracts.RiskFactor(contracts.RiskFactorType.RATE, tenor="5Y")
    scenario = contracts.Scenario(
        scenario_id="rate_up",
        name="rate +1bp",
        category="sensitivity",
        shocks=(contracts.Shock(contracts.RiskFactorType.RATE, 0.0001),),
    )
    context = contracts.ValuationContext(
        valuation_date=date(2026, 9, 1),
        market_data_date=date(2026, 9, 1),
        curve="flat",
        model=model.name,
        assumption=(),
        engine_version="0.5.0",
        portfolio_id=portfolio.portfolio_id,
        instrument_id=instrument.instrument_id,
        trade_id=trade.trade_id,
    )
    result = contracts.RiskResult(analytic="PRICE", payload={"pv": 600_000.0}, context={})
    assert product.kind is contracts.ProductKind.BOND
    assert product.instrument is instrument
    assert trade.instrument.instrument_id == position.security_code
    assert portfolio.kind is contracts.PortfolioKind.LIVE
    assert snapshot.market is market
    assert factor.tenor == "5Y"
    assert scenario.shocks[0].value == 0.0001
    assert context.portfolio_id == "TEST001"
    assert result.validation_status == "UNVALIDATED"
    assert product.value(market, model) == 100.0


def test_resolve_routes_bond_irs_var_mmf() -> None:
    engine = import_module("3_riskengine").RiskEngine()
    contracts = import_module("3_riskengine.core.contracts")
    bond = engine.resolve(contracts.ProductKind.BOND, contracts.AnalyticKind.PRICE)
    irs = engine.resolve("IRS", "PRICE")
    var = engine.resolve(contracts.ProductKind.EQUITY, contracts.AnalyticKind.VAR)
    mmf = engine.resolve(contracts.ProductKind.MMF, "PRICE")
    xva = engine.resolve(contracts.ProductKind.IRS, "XVA")
    assert bond.adapter == "financepy"
    assert irs.adapter == "ore"
    assert var.adapter == "riskfolio"
    assert mmf.adapter == "riskengine"
    assert xva.adapter == "ore"


def test_lineage_context_has_required_keys() -> None:
    contracts = import_module("3_riskengine.core.contracts")
    ctx = contracts.lineage_context(
        valuation_date=date(2026, 9, 1),
        engine_version="0.5.0",
        portfolio_id="TEST001",
    )
    for key in contracts.RESULT_LINEAGE_KEYS:
        assert key in ctx
    assert ctx["validation_status"] == "UNVALIDATED"
    assert ctx["portfolio_id"] == "TEST001"


def test_business_and_processing_api_do_not_import_vendors() -> None:
    roots = [ROOT / "4_business", ROOT / "2_processing" / "api"]
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for needle in FORBIDDEN:
                if needle in text:
                    offenders.append(f"{path.relative_to(ROOT)}:{needle}")
    assert offenders == []
