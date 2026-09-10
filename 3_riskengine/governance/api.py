"""Governance: limits + validation. Not a trade instruction."""
from __future__ import annotations

from typing import Any

from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION


class GovernanceAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def review(self) -> dict[str, Any]:
        limits = self._bound.limits().evaluate()
        validation = self._bound.validation().run()
        mmf = self._bound.liquidity().mmf()
        mmf_ok = (not mmf.get("is_mmf")) or mmf.get("status") != "breach"
        passed = bool(limits.get("passed", limits.get("state") == "GREEN")) and validation.status == "PASS" and mmf_ok
        return {
            "analytic": "GOVERNANCE",
            "engine": RISKENGINE_NAME,
            "engine_version": RISKENGINE_VERSION,
            "is_trade_instruction": False,
            "passed": passed,
            "limits": limits,
            "validation": {"status": validation.status, "checks": validation.checks},
            "mmf": mmf,
        }
