"""Stress Testing business module."""
from __future__ import annotations

from typing import Any

from ..engine import ProfessionalRiskEngine
from ..financepy_adapter import FINANCEPY_CORE_CALLS
from ..models import Scenario
from .common import implemented_by


def run(engine: ProfessionalRiskEngine, scenario: Scenario) -> dict[str, Any]:
    """Run a historical or hypothetical severe multi-factor stress."""

    report = engine.scenario(scenario)
    report["analytic"] = "STRESS"
    return implemented_by(
        report,
        "risk_testing.analytics.stress.run",
        list(FINANCEPY_CORE_CALLS),
        "simultaneous cross-asset stress and trade-level PnL aggregation",
    )
