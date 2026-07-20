"""投資風險分析純計算單元測試。"""
from datetime import date
from importlib import import_module

import pytest

analysis = import_module("2_processing.tools.performance.investment_analysis")
_beta = analysis._beta
_daily_returns = analysis._daily_returns
_performance_periods = analysis._performance_periods
_return_between = analysis._return_between


def test_daily_and_interval_returns() -> None:
    points = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 2), 102.0),
        (date(2026, 1, 3), 101.0),
    ]

    daily = _daily_returns(points)

    assert daily[date(2026, 1, 2)] == pytest.approx(0.02)
    assert daily[date(2026, 1, 3)] == pytest.approx(101 / 102 - 1)
    assert _return_between(points) == pytest.approx(0.01)


def test_beta_uses_only_common_dates() -> None:
    benchmark = {
        date(2026, 1, 2): 0.01,
        date(2026, 1, 3): -0.02,
        date(2026, 1, 4): 0.03,
    }
    asset = {
        date(2026, 1, 2): 0.02,
        date(2026, 1, 3): -0.04,
        date(2026, 1, 4): 0.06,
        date(2026, 1, 5): 0.50,
    }

    value, sample_size = _beta(asset, benchmark)

    assert value == pytest.approx(2.0)
    assert sample_size == 3


def test_performance_periods_include_daily_and_since_inception() -> None:
    history = [
        {"evaluate_date": date(2025, 12, 31), "nav": 100.0},
        {"evaluate_date": date(2026, 1, 2), "nav": 101.0},
        {"evaluate_date": date(2026, 3, 31), "nav": 110.0},
    ]

    periods = {row["period"]: row for row in _performance_periods(history)}

    assert periods["1日"]["return_pct"] == pytest.approx(110 / 101 * 100 - 100)
    assert periods["年初至今"]["return_pct"] == pytest.approx(10.0)
    assert periods["成立以來"]["return_pct"] == pytest.approx(10.0)
