"""Unit tests for valuation/P&L pure math (no DB)."""
from importlib import import_module

import pytest

valuation = import_module("2_processing.api.routers.valuation")


def test_cumulative_return_compounds() -> None:
    result = valuation._cumulative_return([0.1, 0.1])
    assert result == pytest.approx(0.21, rel=1e-9)


def test_cumulative_return_empty_is_zero() -> None:
    assert valuation._cumulative_return([]) == 0.0


def test_nav_index_levels() -> None:
    index = valuation._nav_index([0.1, -0.1])
    assert index[0] == pytest.approx(1.1)
    assert index[1] == pytest.approx(1.1 * 0.9)


def test_max_drawdown_detects_trough() -> None:
    # Peak 1.2 then trough 0.9 → drawdown = 0.9/1.2 - 1 = -0.25
    dd = valuation._max_drawdown([1.0, 1.2, 0.9, 1.05])
    assert dd == pytest.approx(-0.25, rel=1e-9)


def test_max_drawdown_monotonic_up_is_zero() -> None:
    assert valuation._max_drawdown([1.0, 1.1, 1.2]) == 0.0


def test_volatility_zero_for_constant() -> None:
    assert valuation._volatility([0.01, 0.01, 0.01]) == 0.0


def test_volatility_positive_and_annualized() -> None:
    vol = valuation._volatility([0.01, -0.01, 0.02, -0.02])
    assert vol > 0


def test_volatility_single_point_is_zero() -> None:
    assert valuation._volatility([0.01]) == 0.0


def test_annualize_scales_up() -> None:
    # 1% over 63 trading days annualizes to roughly (1.01)^4 - 1.
    ann = valuation._annualize(0.01, 63)
    assert ann == pytest.approx((1.01) ** (252 / 63) - 1, rel=1e-9)


def test_annualize_zero_days() -> None:
    assert valuation._annualize(0.05, 0) == 0.0
