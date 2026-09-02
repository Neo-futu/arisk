"""Key Rate Duration business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_CORE_CALLS
from .common import implemented_by


def run(engine: ProfessionalRiskEngine, bump_bps: float) -> dict[str, Any]:
    """Compute bucketed PV01 and KRD by FinancePy curve bump/revaluation."""

    return implemented_by(
        engine.krd(bump_bps),
        "risk_testing.analytics.krd.run",
        list(FINANCEPY_CORE_CALLS),
        "tenor-isolated FinancePy DiscountCurveFlat.bump_parallel revaluation",
    )
