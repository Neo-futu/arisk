"""CVA/DVA/FVA/MVA business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_FLAT_CURVE_CLASS
from .common import implemented_by


_XVA_FINANCEPY_CALLS = [
    "financepy.utils.date.Date",
    FINANCEPY_FLAT_CURVE_CLASS,
    "FlatDiscountCurve.df_t",
]


def run(
    engine: ProfessionalRiskEngine,
    counterparty_hazard: float,
    own_hazard: float,
    recovery_rate: float,
    funding_spread: float,
    initial_margin_pct: float,
    mva_funding_spread: float,
) -> dict[str, Any]:
    """Integrate discounted EPE/ENE into CVA, DVA, FVA and MVA."""

    return implemented_by(
        engine.xva(
            counterparty_hazard,
            own_hazard,
            recovery_rate,
            funding_spread,
            initial_margin_pct,
            mva_funding_spread,
        ),
        "risk_testing.analytics.xva.run",
        _XVA_FINANCEPY_CALLS,
        "deterministic EPE/ENE default and funding integration discounted by FinancePy curves",
    )
