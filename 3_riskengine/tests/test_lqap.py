"""LQAP horizon aggregation stays inside the risk engine."""
from __future__ import annotations

from importlib import import_module

from .fixtures import sample_snapshot


def test_lqap_bins_cost_and_not_covered() -> None:
    lqap = import_module("3_riskengine.liquidity.lqap")
    result = lqap.analyze(
        [
            {
                "security_code": "CASH",
                "market_value": 100.0,
                "liq_horizon_days": 0,
                "bid_ask_spread": 0.0,
                "expected_daily_volume": 1000.0,
                "liquidity_sector": "CASH",
                "sector_score": 100,
                "price_volatility": 0.0,
            },
            {
                "security_code": "BOND",
                "market_value": 300.0,
                "liq_horizon_days": 12,
                "bid_ask_spread": 0.001,
                "expected_daily_volume": 50.0,
                "liquidity_sector": "IG CORP",
                "sector_score": 40,
                "price_volatility": 0.03,
            },
            {"security_code": "UNKNOWN", "market_value": 50.0},
        ],
        scenario_code="CUSTOM",
        redemption_pct=100,
        cost_multiple=1,
        include_current_day=True,
    )
    by_id = {row["id"]: row for row in result["horizons"]}
    assert by_id["le1"]["positions"] == 1
    assert by_id["d10_15"]["positions"] == 1
    assert by_id["not_covered"]["positions"] == 1
    assert by_id["not_covered"]["market_value"] == 50
    assert result["overview"]["positions"] == 3
    assert result["overview"]["market_value"] == 450
    assert result["redemption"]["cost"] == 0.3
    assert result["overview"]["annual_volatility"] == 2.25
    assert result["lqa_present_count"] == len(lqap.LQA_FIELDS)
    assert result["scenario"]["code"] == "CUSTOM"
    assert len(result["securities"]) == 3
    assert result["securities"][0]["scenario_lqdty_class"]


def test_lqap_via_liquidity_api() -> None:
    engine = import_module("3_riskengine")
    bound = engine.RiskEngine().bind(sample_snapshot())
    stamped = bound.liquidity().lqap(
        [{"security_code": "X", "market_value": 10, "hk_sfc_port_lqdty_class": "2-7 days"}],
        scenario_code="MILD",
    )
    assert stamped["analytic"] == "LQAP"
    assert stamped["model"] == "bloomberg_lqap"
    assert stamped["not_covered_positions"] == 0
