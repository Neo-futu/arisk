"""VaR/CVaR Backtesting business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from .common import implemented_by


def run(
    engine: ProfessionalRiskEngine,
    confidence: float,
    window: int,
) -> dict[str, Any]:
    """Run rolling VaR/CVaR exceptions and Kupiec unconditional coverage."""

    return implemented_by(
        engine.var_backtest(confidence, window),
        "risk_testing.analytics.var_backtest.run",
        [],
        "NumPy historical quantiles, Expected Shortfall and Kupiec likelihood ratio over ARISK NAV market history",
    )
