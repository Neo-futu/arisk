"""Brinson / Campisi 纯模型测试：单期、多期、分标签。"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.performance.models.brinson import brinson
from tools.performance.models.campisi import campisi, interpolate_yield
from tools.performance.models.contribution import carino_factors, contribution

DAY = date(2026, 6, 25)
DAY2 = date(2026, 6, 26)


def _book(day, symbol, weight, ret, asset, industry):
    return {
        "date": day,
        "symbol": symbol,
        "weight": weight,
        "return_period": ret,
        "asset": asset,
        "industry": industry,
    }


def test_bhb_single_period_asset_groups_add_up():
    portfolio = [
        _book(DAY, "EQ1", 0.6, 0.10, "股票", "科技"),
        _book(DAY, "BD1", 0.4, 0.02, "债券", "利率"),
    ]
    benchmark = [
        _book(DAY, "EQB", 0.5, 0.08, "股票", "科技"),
        _book(DAY, "BDB", 0.5, 0.03, "债券", "利率"),
    ]
    result = brinson(portfolio, benchmark, method="BHB", group_by="asset")
    assert result["portfolio_return"] == pytest.approx(0.068)
    assert result["benchmark_return"] == pytest.approx(0.055)
    assert result["active_return"] == pytest.approx(0.013)
    assert result["allocation"] == pytest.approx(0.005)
    assert result["selection"] == pytest.approx(0.005)
    assert result["interaction"] == pytest.approx(0.003)
    assert result["allocation"] + result["selection"] + result["interaction"] == pytest.approx(
        result["active_return"]
    )


def test_bf_absorbs_interaction_into_selection():
    portfolio = [
        _book(DAY, "EQ1", 0.6, 0.10, "股票", "科技"),
        _book(DAY, "BD1", 0.4, 0.02, "债券", "利率"),
    ]
    benchmark = [
        _book(DAY, "EQB", 0.5, 0.08, "股票", "科技"),
        _book(DAY, "BDB", 0.5, 0.03, "债券", "利率"),
    ]
    result = brinson(portfolio, benchmark, method="BF", group_by="asset")
    assert result["interaction"] == pytest.approx(0.0)
    assert result["allocation"] == pytest.approx(0.005)
    assert result["selection"] == pytest.approx(0.008)
    assert result["allocation"] + result["selection"] == pytest.approx(result["active_return"])


def test_brinson_symbol_industry_and_portfolio_labels():
    portfolio = [
        _book(DAY, "EQ1", 0.6, 0.10, "股票", "科技"),
        _book(DAY, "EQ2", 0.4, 0.00, "股票", "金融"),
    ]
    benchmark = [
        _book(DAY, "EQB", 1.0, 0.05, "股票", "科技"),
    ]
    by_symbol = brinson(portfolio, benchmark, method="BHB", group_by="symbol")
    by_industry = brinson(portfolio, benchmark, method="BHB", group_by="industry")
    overall = brinson(portfolio, benchmark, method="BHB", group_by="portfolio")
    assert {row["group"] for row in by_symbol["groups"]} == {"EQ1", "EQ2", "EQB"}
    assert {row["group"] for row in by_industry["groups"]} >= {"科技", "金融"}
    assert overall["groups"][0]["group"] == "PORTFOLIO"
    assert overall["allocation"] == pytest.approx(0.0)
    assert overall["selection"] == pytest.approx(overall["active_return"])
    # 行业与单券的效应之和都等于组合超额
    for result in (by_symbol, by_industry, overall):
        assert (
            result["allocation"] + result["selection"] + result["interaction"]
        ) == pytest.approx(result["active_return"])


def test_brinson_grap_multi_period_matches_wealth_gap():
    portfolio = [
        _book(DAY, "EQ", 1.0, 0.10, "股票", "科技"),
        _book(DAY2, "EQ", 1.0, 0.05, "股票", "科技"),
    ]
    benchmark = [
        _book(DAY, "EQ", 1.0, 0.04, "股票", "科技"),
        _book(DAY2, "EQ", 1.0, 0.02, "股票", "科技"),
    ]
    result = brinson(
        portfolio,
        benchmark,
        method="BHB",
        multi_period=True,
        multi_period_method="grap",
        group_by="portfolio",
    )
    wealth_gap = (1.10 * 1.05) - (1.04 * 1.02)
    assert result["multi_period"] is True
    assert result["active_return"] == pytest.approx(wealth_gap)
    assert (
        result["allocation"] + result["selection"] + result["interaction"]
    ) == pytest.approx(wealth_gap)
    summed = brinson(
        portfolio,
        benchmark,
        method="BHB",
        multi_period=True,
        multi_period_method="sum",
        group_by="portfolio",
    )
    assert summed["active_return"] == pytest.approx(0.06 + 0.03)


def test_brinson_industry_within_asset():
    portfolio = [
        _book(DAY, "EQ1", 0.5, 0.10, "股票", "科技"),
        _book(DAY, "EQ2", 0.5, 0.02, "股票", "金融"),
    ]
    benchmark = [
        _book(DAY, "EQB", 0.5, 0.04, "股票", "科技"),
        _book(DAY, "EQC", 0.5, 0.04, "股票", "金融"),
    ]
    result = brinson(
        portfolio,
        benchmark,
        method="BHB",
        group_by="asset",
        industry_within_assets=["股票"],
    )
    nested = result["industry_within"]["股票"]
    assert nested["group_by"] == "industry"
    assert nested["active_return"] == pytest.approx(result["active_return"])


def test_campisi_without_benchmark_identity():
    rows = [
        {
            "date": DAY,
            "symbol": "B1",
            "weight": 1.0,
            "industry": "信用",
            "asset": "债券",
            "total_return": 0.02,
            "income": 0.03,
            "duration": 5.0,
            "treasury_change": 0.01,
            "convexity": 20.0,
        }
    ]
    plain = campisi(rows, benchmark=False, convexity=False, group_by="industry")
    assert plain["treasury"] == pytest.approx(-0.05)
    assert plain["income"] + plain["treasury"] + plain["spread"] == pytest.approx(plain["total_return"])
    assert plain["selection"] == pytest.approx(0.0)
    curved = campisi(rows, benchmark=False, convexity=True)
    assert curved["treasury"] == pytest.approx(-0.049)
    assert curved["income"] + curved["treasury"] + curved["spread"] == pytest.approx(0.02)


def test_campisi_with_benchmark_selection_is_residual():
    rows = [
        {
            "date": DAY,
            "symbol": "B1",
            "weight": 1.0,
            "industry": "信用",
            "asset": "债券",
            "total_return": 0.02,
            "income": 0.03,
            "duration": 5.0,
            "treasury_change": 0.01,
            "spread_change": -0.002,
        }
    ]
    result = campisi(rows, benchmark=True, convexity=False, group_by="symbol")
    assert result["treasury"] == pytest.approx(-0.05)
    assert result["spread"] == pytest.approx(0.01)
    assert result["selection"] == pytest.approx(0.02 - 0.03 - (-0.05) - 0.01)
    assert (
        result["income"] + result["treasury"] + result["spread"] + result["selection"]
    ) == pytest.approx(result["total_return"])


def test_campisi_multi_period_links_total_return():
    rows = [
        {
            "date": DAY,
            "symbol": "B1",
            "weight": 1.0,
            "industry": "利率",
            "total_return": 0.01,
            "income": 0.004,
            "duration": 2.0,
            "treasury_change": 0.0,
        },
        {
            "date": DAY2,
            "symbol": "B1",
            "weight": 1.0,
            "industry": "利率",
            "total_return": 0.02,
            "income": 0.004,
            "duration": 2.0,
            "treasury_change": 0.0,
        },
    ]
    result = campisi(rows, benchmark=False, multi_period=True, group_by="portfolio")
    assert result["total_return"] == pytest.approx((1.01 * 1.02) - 1)
    assert result["income"] + result["treasury"] + result["spread"] == pytest.approx(result["total_return"])


def test_interpolate_yield():
    curve = [(1.0, 0.02), (10.0, 0.04)]
    assert interpolate_yield(curve, 5.5) == pytest.approx(0.02 + 0.02 * 4.5 / 9)
    assert interpolate_yield(curve, 0.2) == pytest.approx(0.02)
    assert interpolate_yield([], 3) is None


def test_contribution_single_period_weights_times_returns():
    rows = [
        {
            "date": DAY,
            "symbol": "A",
            "security_name": "Alpha",
            "weight": 0.05,
            "return_period": 0.10,
            "asset": "股票",
            "industry": "科技",
        },
        {
            "date": DAY,
            "symbol": "B",
            "security_name": "Beta",
            "weight": 0.95,
            "return_period": 0.02,
            "asset": "债券",
            "industry": "利率",
        },
    ]
    result = contribution(rows, mode="single", group_by="symbol")
    by_symbol = {row["group"]: row for row in result["groups"]}
    assert by_symbol["A"]["contribution"] == pytest.approx(0.005)
    assert by_symbol["B"]["contribution"] == pytest.approx(0.019)
    assert result["contribution_total"] == pytest.approx(0.024)
    assert result["portfolio_return"] == pytest.approx(0.024)
    assert result["residual"] == pytest.approx(0.0)


def test_contribution_groups_sum_to_portfolio():
    rows = [
        {"date": DAY, "symbol": "A", "weight": 0.6, "return_period": 0.10, "asset": "股票", "industry": "科技"},
        {"date": DAY, "symbol": "B", "weight": 0.4, "return_period": 0.02, "asset": "债券", "industry": "利率"},
    ]
    asset = contribution(rows, mode="single", group_by="asset")
    assert sum(row["contribution"] for row in asset["groups"]) == pytest.approx(asset["portfolio_return"])


def test_contribution_carino_links_to_geometric_portfolio_return():
    rows = [
        {"date": DAY, "symbol": "A", "weight": 0.5, "return_period": 0.10, "asset": "股票", "industry": "科技"},
        {"date": DAY, "symbol": "B", "weight": 0.5, "return_period": 0.00, "asset": "债券", "industry": "利率"},
        {"date": DAY2, "symbol": "A", "weight": 0.5, "return_period": 0.04, "asset": "股票", "industry": "科技"},
        {"date": DAY2, "symbol": "B", "weight": 0.5, "return_period": 0.02, "asset": "债券", "industry": "利率"},
    ]
    # 日1组合 5%，日2组合 3% → 几何 8.15%
    result = contribution(rows, mode="daily", link_method="carino", group_by="symbol")
    expected = (1.05 * 1.03) - 1.0
    assert result["portfolio_return"] == pytest.approx(expected)
    assert result["contribution_total"] == pytest.approx(expected)
    assert result["residual"] == pytest.approx(0.0)
    from math import log

    _kappas, scale = carino_factors([0.05, 0.03])
    assert scale == pytest.approx(1.0 / (log(1.0 + expected) / expected))


def test_contribution_average_uses_mean_weight_times_cum_return():
    rows = [
        {"date": DAY, "symbol": "A", "weight": 0.4, "return_period": 0.10, "asset": "股票", "industry": "科技"},
        {"date": DAY2, "symbol": "A", "weight": 0.6, "return_period": 0.05, "asset": "股票", "industry": "科技"},
    ]
    result = contribution(rows, mode="average", group_by="symbol")
    row = result["groups"][0]
    assert row["weight"] == pytest.approx(0.5)
    assert row["return_period"] == pytest.approx(1.10 * 1.05 - 1.0)
    assert row["contribution"] == pytest.approx(0.5 * (1.10 * 1.05 - 1.0))
