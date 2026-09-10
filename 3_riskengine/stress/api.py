"""Stress testing on platform snapshots (multi-factor simultaneous revaluation)."""
from __future__ import annotations

from typing import Any


class StressAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def run(self, scenario: Any) -> dict[str, Any]:
        from ..risk.testing import stress as run

        return run(self._bound, scenario)

    def reverse(
        self,
        scenario: Any,
        target_loss_pct_nav: float,
        max_scale: float = 20.0,
    ) -> dict[str, Any]:
        from ..risk.testing import reverse_stress as run

        return run(self._bound, scenario, target_loss_pct_nav, max_scale)


def run(snapshot: Any, scenario: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).stress().run(scenario)
