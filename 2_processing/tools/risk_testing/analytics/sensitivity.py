"""Sensitivity Testing business module."""
from __future__ import annotations

from typing import Iterable, Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_CORE_CALLS
from ..models import Shock
from .common import implemented_by


def run(engine: ProfessionalRiskEngine, shocks: Iterable[Shock]) -> dict[str, Any]:
    """Run one-factor-at-a-time PV, Delta and Gamma revaluation."""

    return implemented_by(
        engine.sensitivity(shocks),
        "risk_testing.analytics.sensitivity.run",
        list(FINANCEPY_CORE_CALLS),
        "central finite differences over FinancePy shocked discount curves",
    )
