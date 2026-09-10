"""RiskEngine kernel modules consume platform snapshots, not a second store."""
from __future__ import annotations

from importlib import import_module

from .fixtures import SCENARIOS, Shock, RiskFactorType, ShockMode, sample_snapshot


def test_instruments_classify_platform_holdings() -> None:
    classify = import_module("3_riskengine.instruments")
    snapshot = sample_snapshot()
    bond = snapshot.positions[0]
    equity = snapshot.positions[1]
    cash = snapshot.positions[2]
    assert classify.is_fixed_income(bond)
    assert classify.is_equity_like(equity)
    assert classify.is_cash_like(cash)
    assert classify.krd_bucket(bond, snapshot.as_of_date) == "5Y"
    assert classify.years_to_maturity(bond, snapshot.as_of_date) == 5.0
    assert classify.factor_family(equity, snapshot.reporting_currency) == "EQUITY+FX"
    mmf_holding = import_module("2_processing.tools.risk_testing.models").Position(
        security_code="EXTMMF",
        security_name="External MMF",
        asset_class="FUND",
        currency="HKD",
        market_value=1.0,
        market_value_base=1.0,
        metadata={"fund_type": "MMF"},
    )
    assert classify.is_mmf(mmf_holding)
    assert classify.product_kind_of(mmf_holding).value == "MMF"
    assert not classify.is_equity_like(mmf_holding)


def test_market_module_uses_canonical_platform_tables() -> None:
    market = import_module("3_riskengine.market")
    assert market.CANONICAL_TABLES["Position"] == "fsi.balance_*"
    assert market.CANONICAL_TABLES["Market"] == "fsi.mktdata_*"
    assert "fsi.balance_portfolio_nav" in market.HOLDING_TABLES
    returns = market.nav_returns(sample_snapshot())
    assert returns.size == 300


def test_bound_engine_exposes_domain_apis() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    assert engine.kernel().value()["base_pv"] == 1_000_000.0
    assert engine.liquidity().ratio()["kpi"] == "Liquidity"
    assert engine.counterparty().exposure()["kpi"] == "Counterparty Exposure"
    assert engine.counterparty().xva()["analytic"] == "XVA"
    mapping = engine.counterparty().ore_mapping()
    assert mapping["trades"]
    stress = engine.stress().run(SCENARIOS["gfc_2008"])
    scenario = engine.scenario().named("fed_hike_75")
    pnl = engine.pnl().revalue((shock,))
    previous = sample_snapshot()
    explain = engine.pnl().explain(previous)
    assert stress["analytic"] == "STRESS"
    assert scenario["analytic"] == "SCENARIO"
    assert pnl["pnl"] < 0.0
    assert explain["analytic"] == "PNL_EXPLAIN"
    assert "engine_version" in stress


def test_financepy_modified_duration_and_ore_mapping() -> None:
    snapshot = sample_snapshot()
    fp = import_module("3_riskengine.adapters.financepy").FinancePyValuationAdapter(
        snapshot.as_of_date
    )
    duration = fp.modified_duration(0.035, 5.0, snapshot.as_of_date)
    ore = import_module("3_riskengine.adapters.ore").OREAdapter()
    mapping = ore.map_snapshot(snapshot)
    xva = ore.xva(
        snapshot,
        fp,
        1_000_000.0,
        counterparty_hazard=0.02,
        own_hazard=0.01,
        recovery_rate=0.40,
        funding_spread=0.01,
        initial_margin_pct=0.05,
        mva_funding_spread=0.008,
    )
    assert duration > 0.0
    assert mapping["base_currency"] == "HKD"
    assert mapping["curves"][0]["engine"] == "ORE"
    assert {item["id"] for item in mapping["trades"]} == {"BOND5Y", "US_EQ", "CASH"}
    assert ore.available is True
    assert ore.ore_swig_available is True
    assert xva["library"] == "ORE"
    assert xva["cva"] > 0.0
    assert 0.0 < xva["exposure_profile"][0]["discount_factor"] < 1.0
    from datetime import date

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
    assert abs(american["delta"] - 0.506123) < 1e-5


def test_professional_engine_delegates_to_riskengine_kernel() -> None:
    snapshot = sample_snapshot()
    legacy = import_module("2_processing.tools.risk_testing").ProfessionalRiskEngine(snapshot)
    kernel = import_module("3_riskengine").RiskEngine().bind(snapshot).kernel()
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    assert legacy.value((shock,))["pnl"] == kernel.value((shock,))["pnl"]
    assert legacy.krd()["library"] == "FinancePy"
