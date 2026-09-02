"""Scenario Testing business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_CORE_CALLS
from ..models import Scenario
from .common import implemented_by


def run(engine: ProfessionalRiskEngine, scenario: Scenario) -> dict[str, Any]:
    """Apply a user-defined or catalogued multi-factor scenario."""

    return implemented_by(
        engine.scenario(scenario),
        "risk_testing.analytics.scenario.run",
        list(FINANCEPY_CORE_CALLS),
        "simultaneous factor shocks with position-level revaluation",
    )
