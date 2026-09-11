"""Reverse Stress Testing business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_CORE_CALLS
from ..models import Scenario
from .common import implemented_by


def run(
    engine: ProfessionalRiskEngine,
    scenario: Scenario,
    target_loss_pct_nav: float,
    max_scale: float,
) -> dict[str, Any]:
    """Solve for the minimum proportional disaster scale that breaches NAV."""

    return implemented_by(
        engine.reverse_stress(scenario, target_loss_pct_nav, max_scale),
        "risk_testing.analytics.reverse_stress.run",
        list(FINANCEPY_CORE_CALLS),
        "bisection root search over repeated FinancePy portfolio revaluations",
    )
