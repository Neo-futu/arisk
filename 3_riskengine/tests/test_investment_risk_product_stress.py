"""投资风险 · 产品压力测试 Tab：LQAP 假设 / Overview / Horizon / Stress / 字段覆盖。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_mmf_snapshot, sample_product_stress_meta, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "LqapPortfolioLiquidity.tsx"
TABS = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "RiskDomainTabs.tsx"


def test_frontend_product_stress_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8") + "\n" + TABS.read_text(encoding="utf-8")
    for token in (
        "getLqaPortfolio",
        "LqapPortfolioLiquidity",
        "Portfolio Liquidity Analytics",
        "Portfolio Overview",
        "Redemption Scenario",
        "Horizon Analysis",
        "Stress Details",
        "redemptionPct",
        "costMultiple",
        "includeCurrentDay",
        "SEVERE",
        "lqa_fields",
        "tabLiquidity",
    ):
        assert token in text, token


def test_product_stress_six_business_modules() -> None:
    ps = import_module("3_riskengine.liquidity.product_stress")
    meta = sample_product_stress_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_mmf_snapshot())
        .liquidity()
        .product_stress(
            meta=meta,
            scenario_code="SEVERE",
            redemption_pct=100.0,
            cost_multiple=0.5,
            include_current_day=True,
        )
    )
    check = ps.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "product-stress"
    assert pack["page"] == "/investment-risk/indicators"
    assert pack["business_modules"] == list(ps.BUSINESS_MODULES)
    assert pack["fund_id"] == "BHMMF001"
    assert pack["currency"] == "USD"

    assumptions = pack["modules"]["assumptions"]
    assert assumptions["scenario"]["code"] == "SEVERE"
    assert assumptions["redemption_pct"] == 100.0
    assert assumptions["cost_multiple"] == 0.5
    assert assumptions["target_cost"] == "Bid-Ask"
    assert assumptions["day_factor"] == pytest.approx(1.4)
    assert assumptions["cost_factor"] == pytest.approx(1.5)

    overview = pack["modules"]["overview"]
    assert overview["market_value"] == pytest.approx(860_885_000.0)
    assert overview["positions"] == 6
    assert overview["liq_horizon_days"] is not None
    assert overview["global_score"] is not None

    redemption = pack["modules"]["redemption"]
    assert redemption["nominal"] == pytest.approx(860_885_000.0)
    assert redemption["residual_market_value"] == pytest.approx(0.0)
    assert redemption["value"] == pytest.approx(redemption["nominal"] - redemption["cost"])

    horizon = pack["modules"]["horizon_analysis"]
    by_id = {row["id"]: row for row in horizon["horizons"]}
    assert by_id["le1"]["mv_weight_pct"] > 0  # overnight deposit
    assert by_id["d1_3"]["mv_weight_pct"] > 0  # corp bonds ~3d under SEVERE stretch or base
    assert by_id["d3_5"]["positions"] >= 1  # reverse repo
    assert by_id["gt25"]["mv_weight_pct"] > 0  # term deposit
    assert horizon["not_covered_positions"] == 0

    stress = pack["modules"]["stress_details"]
    assert stress["count"] == 6
    assert all(row["cost"] is not None for row in stress["securities"])

    coverage = pack["modules"]["field_coverage"]
    assert coverage["lqa_present_count"] == 15
    assert coverage["lqa_populated_fields"] == 15
    assert coverage["lqa_proxy_positions"] == 6
    assert pack["lqa_populated_fields"] == 15

    # HTTP 同形
    assert pack["overview"]["market_value"] == overview["market_value"]
    assert pack["horizons"]
    assert pack["securities"]


def test_fi_bid_ask_ladder_not_adtv() -> None:
    fields = import_module("3_riskengine.liquidity.lqa_fields")
    row = fields.enrich_position(
        {
            "security_code": "BOND1",
            "asset_category": "BOND_CORP",
            "market_value": 10_000_000.0,
            "duration": 5.0,
        },
        bid_ask_bps=3.0,
        adtv={"adtv_30d": 1.0, "sample_days": 30},  # 故意给极小 ADTV，不应驱动天数
        as_of_date="2026-06-25",
    )
    assert row["horizon_model"] == "bid_ask"
    assert row["liq_horizon_days"] == pytest.approx(1.0)  # ≤10bp → 1d
    # 若误走参与率：10e6/(1*0.1)=1e8 天
    assert row["liq_horizon_days"] < 100


def test_equity_participation_path() -> None:
    fields = import_module("3_riskengine.liquidity.lqa_fields")
    row = fields.enrich_position(
        {
            "security_code": "0700.HK",
            "asset_category": "EQUITY",
            "market_value": 10_000_000.0,
        },
        adtv={"adtv_30d": 5_000_000.0, "sample_days": 30},
        as_of_date="2026-06-25",
    )
    assert row["horizon_model"] == "participation"
    # MV / (EDV * 10%) = 10e6 / 5e5 = 20
    assert row["liq_horizon_days"] == pytest.approx(20.0)


def test_severe_stretches_days_and_cost() -> None:
    lqap = import_module("3_riskengine.liquidity.lqap")
    positions = [
        {
            "security_code": "B",
            "market_value": 1_000_000.0,
            "liq_horizon_days": 10.0,
            "bid_ask_spread": 0.0003,
            "expected_daily_volume": 0.0,
            "sector_score": 50,
            "liquidity_sector": "Corporate",
            "price_volatility": 0.05,
            "asset_category": "BOND_CORP",
        }
    ]
    mild = lqap.analyze(positions, scenario_code="CUSTOM", redemption_pct=100, cost_multiple=0.5)
    severe = lqap.analyze(positions, scenario_code="SEVERE", redemption_pct=100, cost_multiple=0.5)
    assert severe["securities"][0]["liq_horizon_days"] == pytest.approx(14.0)  # 10 * 1.4
    assert severe["redemption"]["cost"] > mild["redemption"]["cost"]


def test_domain_liquidity_includes_product_stress() -> None:
    pack = import_module("4_business.investment_risk.liquidity").analyze(sample_snapshot())
    assert pack["domain"] == "liquidity"
    assert "product_stress" in pack
    assert pack["product_stress"]["modules"]["field_coverage"]["lqa_present_count"] == 15
