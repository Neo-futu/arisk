"""Model-validation tests for the standalone FinancePy risk engine."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from importlib import import_module

engine_module = import_module("2_processing.tools.risk_testing.engine")
models_module = import_module("2_processing.tools.risk_testing.models")
scenario_module = import_module("2_processing.tools.risk_testing.scenarios")
router_module = import_module("2_processing.api.routers.risk_testing")
analytics_module = import_module("2_processing.tools.risk_testing.analytics")
market_data_module = import_module("2_processing.tools.risk_testing.market_data")

ProfessionalRiskEngine = engine_module.ProfessionalRiskEngine
PortfolioSnapshot = models_module.PortfolioSnapshot
Position = models_module.Position
RiskFactorType = models_module.RiskFactorType
Shock = models_module.Shock
ShockMode = models_module.ShockMode
SCENARIOS = scenario_module.SCENARIOS
HistoricalAssetSeries = market_data_module.HistoricalAssetSeries
HistoricalMarketData = market_data_module.HistoricalMarketData


def sample_snapshot(as_of: date = date(2026, 9, 1), equity_value: float = 300_000.0) -> PortfolioSnapshot:
    """Create deterministic cross-asset data for quantitative regression tests."""

    returns = []
    for index in range(300):
        value = ((index % 17) - 8) * 0.00035
        if index in {90, 180, 270}:
            value = -0.025
        returns.append((as_of - timedelta(days=299 - index), value))
    return PortfolioSnapshot(
        fund_id="TEST001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[
            Position(
                security_code="BOND5Y",
                security_name="Five Year Bond",
                asset_class="BOND",
                currency="HKD",
                market_value=600_000.0,
                market_value_base=600_000.0,
                duration=4.5,
                convexity=20.0,
                ytm=0.035,
                coupon_rate=0.03,
                maturity_date=as_of + timedelta(days=365 * 5),
            ),
            Position(
                security_code="US_EQ",
                security_name="US Equity",
                asset_class="EQUITY",
                currency="USD",
                market_value=equity_value / 7.8,
                market_value_base=equity_value,
                fx_rate=7.8,
            ),
            Position(
                security_code="CASH",
                security_name="Cash",
                asset_class="CASH",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
            ),
        ],
        nav_returns=returns,
        data_quality={"position_count": 3, "source": "test"},
    )


def test_financepy_rate_revaluation_and_krd() -> None:
    """A positive rate shock must reduce bond PV and populate the 5Y KRD bucket."""

    engine = ProfessionalRiskEngine(sample_snapshot())
    valuation = engine.value((Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),))
    krd = engine.krd(1.0)
    assert valuation["pnl"] < 0.0
    bucket = next(item for item in krd["buckets"] if item["tenor"] == "5Y")
    assert bucket["pv01"] < 0.0
    assert bucket["key_rate_duration"] > 0.0
    assert krd["library"] == "FinancePy"


def test_sensitivity_and_multifactor_scenario() -> None:
    """Sensitivity returns Greeks and a crisis scenario produces a loss."""

    engine = ProfessionalRiskEngine(sample_snapshot())
    sensitivity = engine.sensitivity((Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE),))
    scenario = engine.scenario(SCENARIOS["gfc_2008"])
    assert sensitivity["sensitivities"][0]["delta"] != 0.0
    assert scenario["pnl"] < 0.0
    assert len(scenario["trade_values"]) == 3


def test_reverse_stress_finds_break_even_scale() -> None:
    """Reverse stress must find a finite scenario multiplier for a reachable target."""

    result = ProfessionalRiskEngine(sample_snapshot()).reverse_stress(
        SCENARIOS["gfc_2008"], target_loss_pct_nav=5.0, max_scale=10.0
    )
    assert result["breach_reached"] is True
    assert 0.0 < result["critical_scale"] <= 10.0
    assert -result["pnl"] == pytest.approx(result["target_loss_amount"], rel=1e-6)


def test_tail_risk_and_var_backtest_are_auditable() -> None:
    """Tail losses increase with sigma and VaR backtest returns coverage diagnostics."""

    engine = ProfessionalRiskEngine(sample_snapshot())
    tail = engine.tail_risk([3.0, 4.0, 5.0], capital_buffer=80_000.0)
    backtest = engine.var_backtest(confidence=0.99, window=60)
    losses = [item["loss_amount"] for item in tail["tail_scenarios"]]
    assert losses == sorted(losses)
    assert tail["expected_shortfall_99_amount"] >= tail["historical_var_99_amount"]
    assert backtest["status"] == "OK"
    assert backtest["observations"] == 240
    assert backtest["traffic_light"] in {"GREEN", "YELLOW", "RED"}
    assert backtest["kupiec_lr"] >= 0.0


def test_pnl_explain_reconciles_and_xva_components() -> None:
    """PnL explain balances to total PnL and XVA exposes all requested adjustments."""

    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    current = sample_snapshot(date(2026, 9, 1), equity_value=300_000.0)
    engine = ProfessionalRiskEngine(current)
    explain = engine.pnl_explain(previous)
    xva = engine.xva(0.02, 0.01, 0.40, 0.01, 0.05, 0.008)
    totals = explain["totals"]
    explained = totals["carry"] + totals["rates"] + totals["fx"] + totals["position"] + totals["residual"]
    assert explained == pytest.approx(totals["total"])
    assert xva["cva"] >= 0.0
    assert xva["dva"] >= 0.0
    assert xva["fva"] >= 0.0
    assert xva["mva"] >= 0.0
    assert len(xva["exposure_profile"]) == 20


def test_xml_configuration_parses_shocks_and_parameters() -> None:
    """XML integration must produce the same validated configuration as JSON."""

    payload = b"""<riskRun analytic="SCENARIO" as_of_date="2026-09-01">
        <scenario id="custom" name="XML multi-factor" />
        <parameters confidence="0.975" lookback_days="300" />
        <shocks>
            <shock factor_type="RATE" value="0.0075" mode="ABSOLUTE" label="rate +75bp" />
            <shock factor_type="EQUITY" value="-0.08" mode="RELATIVE" label="equity -8%" />
        </shocks>
    </riskRun>"""
    request = router_module._xml_request(payload)
    assert request.analytic.value == "SCENARIO"
    assert request.confidence == pytest.approx(0.975)
    assert request.lookback_days == 300
    assert len(request.shocks) == 2
    assert request.shocks[0].value == pytest.approx(0.0075)


def test_historical_backtest_supports_current_and_custom_weights() -> None:
    """Historical replay must use current holdings or normalized user-adjusted weights."""

    snapshot = sample_snapshot()
    start = date(2026, 8, 3)
    end = date(2026, 9, 1)
    market = HistoricalMarketData(
        start_date=start,
        end_date=end,
        source_tables=("fsi.mktdata_quotes", "fsi.mktdata_bond_risk"),
        series=(
            HistoricalAssetSeries(
                "BOND5Y", "Five Year Bond", "BOND",
                ((start, 100.0), (end, 95.0)),
                "fsi.mktdata_bond_risk", "REAL_MARKET", True,
            ),
            HistoricalAssetSeries(
                "US_EQ", "US Equity", "EQUITY",
                ((start, 100.0), (end, 110.0)),
                "fsi.mktdata_quotes", "REAL_MARKET", True,
            ),
            HistoricalAssetSeries(
                "CASH", "Cash", "CASH",
                ((start, 1.0), (end, 1.0)),
                "constant_value", "ZERO_RETURN_PROXY", False,
            ),
        ),
    )
    current = analytics_module.historical_backtest.run(snapshot, market, "CURRENT")
    adjusted = analytics_module.historical_backtest.run(
        snapshot,
        market,
        "CUSTOM",
        {"BOND5Y": 0.0, "US_EQ": 50.0, "CASH": 50.0},
    )
    assert current["total_return_pct"] == pytest.approx(0.0)
    assert adjusted["total_return_pct"] == pytest.approx(5.0)
    assert adjusted["data_quality"]["real_market_weight_pct"] == pytest.approx(50.0)
    assert adjusted["data_quality"]["proxy_weight_pct"] == pytest.approx(50.0)
    assert adjusted["implementation"]["financepy_calls"] == []


def test_each_submenu_business_module_is_callable_and_auditable() -> None:
    """Every submenu owns a Python run function and implementation metadata."""

    current = sample_snapshot()
    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    engine = ProfessionalRiskEngine(current)
    reports = [
        analytics_module.sensitivity.run(
            engine,
            (Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),),
        ),
        analytics_module.stress.run(engine, SCENARIOS["gfc_2008"]),
        analytics_module.scenario.run(engine, SCENARIOS["fed_hike_75"]),
        analytics_module.reverse_stress.run(engine, SCENARIOS["gfc_2008"], 5.0, 10.0),
        analytics_module.tail_risk.run(engine, [3.0, 4.0, 5.0], 80_000.0),
        analytics_module.krd.run(engine, 1.0),
        analytics_module.pnl_explain.run(engine, previous),
        analytics_module.historical_backtest.run(
            current,
            HistoricalMarketData(
                start_date=date(2026, 8, 1),
                end_date=date(2026, 9, 1),
                source_tables=("test",),
                series=tuple(
                    HistoricalAssetSeries(
                        item.security_code,
                        item.security_name,
                        item.asset_class,
                        ((date(2026, 8, 1), 1.0), (date(2026, 9, 1), 1.01)),
                        "test",
                        "REAL_MARKET",
                        True,
                    )
                    for item in current.positions
                ),
            ),
        ),
        analytics_module.var_backtest.run(engine, 0.99, 60),
        analytics_module.xva.run(engine, 0.02, 0.01, 0.40, 0.01, 0.05, 0.008),
    ]
    assert len(reports) == 10
    for report in reports:
        implementation = report["implementation"]
        assert implementation["business_module"].startswith("risk_testing.analytics.")
        assert isinstance(implementation["financepy_calls"], list)
        assert implementation["portfolio_data_module"] == "risk_testing.portfolio_data"
        assert implementation["market_data_module"] == "risk_testing.market_data"
