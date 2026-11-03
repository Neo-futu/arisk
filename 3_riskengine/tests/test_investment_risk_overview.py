"""投资风险组合概况：组合 / 区间收益 / 资产配置 / Top10 股债 / 行业。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_overview_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "routes" / "_layout" / "investment-risk.overview.tsx"


def test_frontend_overview_surfaces_business_modules() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "getPortfolioOverview",
        "performance",
        "asset_allocation",
        "top_stocks",
        "top_bonds",
        "stock_sectors",
        "allocationStructure",
        "returnTrend",
    ):
        assert token in text, token


def test_overview_six_business_modules() -> None:
    overview = import_module("3_riskengine.portfolio.overview")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .portfolio()
        .overview(meta={"port_name": "Overview Book", "portfolio_type": "MIXED", "unit_nav": 1.02})
    )
    check = overview.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["business_modules"] == list(overview.BUSINESS_MODULES)

    portfolio = pack["modules"]["portfolio"]
    assert portfolio["fund_id"] == "OVW001"
    assert portfolio["net_asset"] == pytest.approx(1_140_000.0)
    assert portfolio["unit_nav"] == pytest.approx(1.02)

    periods = {row["period"] for row in pack["performance"]}
    assert {"1日", "1月", "3月", "成立以来"} <= periods
    assert all("return_pct" in row for row in pack["performance"])

    classes = {row["asset_class"] for row in pack["asset_allocation"]}
    assert "STOCK" in classes
    assert "BOND_CORP" in classes or "BOND" in classes
    assert "CASH" in classes
    assert sum(row["weight_pct"] for row in pack["asset_allocation"]) == pytest.approx(100.0, abs=0.05)

    assert len(pack["top_stocks"]) >= 2
    assert pack["top_stocks"][0]["market_value_base"] >= pack["top_stocks"][-1]["market_value_base"]
    assert "sector" in pack["top_stocks"][0]

    assert len(pack["top_bonds"]) >= 2
    assert pack["top_bonds"][0]["security_code"] in {"BOND5Y", "CORP3Y"}
    assert pack["top_bonds"][0]["ytm"] is not None

    sectors = {row["sector"] for row in pack["stock_sectors"]}
    assert "信息技术" in sectors
    assert "金融" in sectors
    assert sum(row["position_count"] for row in pack["stock_sectors"]) == len(pack["top_stocks"])


def test_performance_periods_math() -> None:
    overview = import_module("3_riskengine.portfolio.overview")
    from datetime import date

    points = [
        (date(2026, 1, 1), 1.0),
        (date(2026, 1, 2), 1.01),
        (date(2026, 2, 1), 1.05),
        (date(2026, 9, 1), 1.10),
    ]
    periods = {row["period"]: row["return_pct"] for row in overview.performance_periods(points)}
    assert periods["1日"] == pytest.approx((1.10 / 1.05 - 1.0) * 100.0)
    assert periods["成立以来"] == pytest.approx(10.0)


def test_domain_overview_includes_engine_pack() -> None:
    pack = import_module("4_business.investment_risk.overview").analyze(sample_snapshot())
    assert pack["domain"] == "overview"
    assert "Gross Exposure" in pack["kpis"]
    assert pack["overview"]["modules"]["asset_allocation"]["rows"]
    assert pack["overview"]["top_stocks"]
    assert pack["overview"]["top_bonds"]
