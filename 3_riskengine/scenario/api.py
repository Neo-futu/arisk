"""Scenario revaluation on platform snapshots."""
from __future__ import annotations

from typing import Any

from .catalog import SCENARIOS, scenario_catalog


class ScenarioAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def catalog(self) -> list[dict[str, object]]:
        return scenario_catalog()

    def run(self, scenario: Any) -> dict[str, Any]:
        from ..risk.testing import scenario as run

        return run(self._bound, scenario)

    def named(self, scenario_id: str) -> dict[str, Any]:
        scenario = SCENARIOS[scenario_id]
        return self.run(scenario)


def run(snapshot: Any, scenario: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).scenario().run(scenario)
