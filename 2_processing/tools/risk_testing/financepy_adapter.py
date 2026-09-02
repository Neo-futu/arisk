"""Explicit FinancePy valuation adapter and auditable call metadata."""
from __future__ import annotations

from datetime import date
from typing import Any

from financepy.utils.date import Date as FinanceDate

try:
    from financepy.market.curves.flat_discount_curve import FlatDiscountCurve as FinancePyFlatCurve
    FINANCEPY_FLAT_CURVE_CLASS = "financepy.market.curves.flat_discount_curve.FlatDiscountCurve"
except ImportError:  # FinancePy <= 1.0.x compatibility
    from financepy.market.curves.discount_curve_flat import DiscountCurveFlat as FinancePyFlatCurve
    FINANCEPY_FLAT_CURVE_CLASS = "financepy.market.curves.discount_curve_flat.DiscountCurveFlat"


FINANCEPY_CORE_CALLS = [
    "financepy.utils.date.Date",
    FINANCEPY_FLAT_CURVE_CLASS,
    "FlatDiscountCurve.df_t",
    "FlatDiscountCurve.bump_parallel",
]


class FinancePyValuationAdapter:
    """Build and shock FinancePy curves for portfolio cash-flow revaluation."""

    def __init__(self, value_date: date):
        self.value_date = FinanceDate(value_date.day, value_date.month, value_date.year)

    def flat_curve(self, zero_rate: float) -> Any:
        """Build a continuously-compounded FinancePy flat discount curve."""

        return FinancePyFlatCurve(self.value_date, max(float(zero_rate), -0.05))

    def discount_factor(self, zero_rate: float, years: float) -> float:
        """Call FinancePy ``DiscountCurveFlat.df_t`` for a cash-flow horizon."""

        return float(self.flat_curve(zero_rate).df_t(max(float(years), 0.0)))

    def shocked_discount_factor(self, zero_rate: float, shock: float, years: float) -> float:
        """Call FinancePy ``bump_parallel`` then ``df_t`` for shocked valuation."""

        base_curve = self.flat_curve(zero_rate)
        base_rate = max(float(zero_rate), -0.05)
        shocked_rate = max(float(zero_rate) + float(shock), -0.05)
        shocked_curve = base_curve.bump_parallel(shocked_rate - base_rate)
        return float(shocked_curve.df_t(max(float(years), 0.0)))


def financepy_usage(
    business_module: str,
    direct_calls: list[str] | None = None,
    supplementary_engine: str | None = None,
) -> dict[str, Any]:
    """Return an auditable implementation descriptor for API and GUI reports."""

    return {
        "business_module": business_module,
        "valuation_adapter": "risk_testing.financepy_adapter.FinancePyValuationAdapter",
        "financepy_calls": direct_calls if direct_calls is not None else list(FINANCEPY_CORE_CALLS),
        "supplementary_engine": supplementary_engine,
        "portfolio_data_module": "risk_testing.portfolio_data",
        "market_data_module": "risk_testing.market_data",
    }
