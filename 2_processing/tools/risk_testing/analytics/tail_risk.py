"""Tail Risk Testing business module."""
from __future__ import annotations

from typing import Any, Iterable

from ..engine import ProfessionalRiskEngine
from .common import implemented_by


def run(
    engine: ProfessionalRiskEngine,
    sigma_levels: Iterable[float],
    capital_buffer: float,
) -> dict[str, Any]:
    """Measure 3σ–5σ losses, historical VaR/ES and capital adequacy."""

    return implemented_by(
        engine.tail_risk(sigma_levels, capital_buffer),
        "risk_testing.analytics.tail_risk.run",
        [],
        "NumPy empirical quantiles/Expected Shortfall over ARISK NAV market history; FinancePy PV is the portfolio valuation foundation",
    )
