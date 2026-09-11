"""Fixed-income revaluation helpers. Discounting goes through FinancePyAdapter."""
from __future__ import annotations

from datetime import date
from typing import Any

from .classify import annual_rate, is_fixed_income, years_to_maturity


def terminal_cashflow(position: Any, as_of: date, financepy: Any) -> float:
    """Implied redemption CF that reprices to current MV at the position YTM."""

    value = float(position.market_value_base)
    if not is_fixed_income(position):
        return value
    years = years_to_maturity(position, as_of)
    base_df = financepy.discount_factor(annual_rate(position), years, as_of)
    return value / base_df if base_df else value


def reprice_fixed_income(
    position: Any,
    as_of: date,
    financepy: Any,
    rate_shift: float,
) -> float:
    """Shock YTM by ``rate_shift`` and re-discount the implied terminal CF."""

    years = years_to_maturity(position, as_of)
    base_rate = annual_rate(position)
    terminal = terminal_cashflow(position, as_of, financepy)
    shocked_df = financepy.shocked_discount_factor(base_rate, rate_shift, years, as_of)
    return float(terminal * shocked_df)
