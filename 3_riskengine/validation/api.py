"""Validation: pricing, greeks, risk, regression and reconciliation."""
from __future__ import annotations

from typing import Any

from ..core.contracts import ValidationResult
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION


class ValidationAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def _context(self) -> dict[str, Any]:
        snapshot = self._bound.snapshot
        return {
            "engine": RISKENGINE_NAME,
            "engine_version": RISKENGINE_VERSION,
            "model": "validation",
            "model_version": RISKENGINE_VERSION,
            "parameters": {},
            "assumptions": [],
            "data_quality": getattr(snapshot, "data_quality", {}),
            "valuation_date": snapshot.as_of_date.isoformat(),
            "market_data_date": snapshot.as_of_date.isoformat(),
        }

    def pricing(self) -> ValidationResult:
        priced = self._bound.valuation().price()
        ok = priced.base_pv > 0 and len(priced.trade_values) == len(self._bound.snapshot.positions)
        return ValidationResult(
            status="PASS" if ok else "FAIL",
            checks=[
                {"name": "positive_base_pv", "passed": priced.base_pv > 0, "value": priced.base_pv},
                {
                    "name": "trade_count_matches_positions",
                    "passed": len(priced.trade_values) == len(self._bound.snapshot.positions),
                    "value": len(priced.trade_values),
                },
            ],
            context=self._context(),
        )

    def greeks(self, shocks: Any) -> ValidationResult:
        report = self._bound.valuation().greeks(shocks)
        rows = report.get("sensitivities") or []
        passed = bool(rows) and all("delta" in row and "gamma" in row for row in rows)
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            checks=[{"name": "greeks_populated", "passed": passed, "count": len(rows)}],
            context=self._context(),
        )

    def risk(self, shocks: Any) -> ValidationResult:
        report = self._bound.risk().sensitivity(shocks)
        passed = report.get("analytic") == "SENSITIVITY"
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            checks=[{"name": "sensitivity_analytic", "passed": passed}],
            context=self._context(),
        )

    def regression(self, shocks: Any) -> ValidationResult:
        """Deterministic direction: a positive rate shock must not increase bond-heavy PV."""

        revalued = self._bound.valuation().revalue(shocks)
        passed = revalued.pnl <= 0.0
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            checks=[{"name": "rate_up_pnl_non_positive", "passed": passed, "pnl": revalued.pnl}],
            context=self._context(),
        )

    def reconciliation(self, previous: Any) -> ValidationResult:
        report = self._bound.valuation().pnl(previous=previous)
        totals = report.get("totals") or {}
        explained = (
            float(totals.get("carry", 0.0))
            + float(totals.get("rates", 0.0))
            + float(totals.get("fx", 0.0))
            + float(totals.get("position", 0.0))
            + float(totals.get("residual", 0.0))
        )
        total = float(totals.get("total", 0.0))
        passed = abs(explained - total) < 1e-6
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            checks=[{"name": "pnl_explain_balances", "passed": passed, "explained": explained, "total": total}],
            context=self._context(),
        )

    def cross_engine(self) -> ValidationResult:
        from .cross_engine import run

        return run(self._bound)

    def run(
        self,
        shocks: Any | None = None,
        previous: Any | None = None,
    ) -> ValidationResult:
        from ..core.contracts import RiskFactorType, Shock, ShockMode

        shocks = shocks or (Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),)
        parts = [
            self.pricing(),
            self.greeks(shocks),
            self.risk(shocks),
            self.regression(shocks),
            self.cross_engine(),
        ]
        if previous is not None:
            parts.append(self.reconciliation(previous))
        checks: list[dict[str, Any]] = []
        for part in parts:
            checks.extend(part.checks)
        passed = all(part.status == "PASS" for part in parts)
        return ValidationResult(
            status="PASS" if passed else "FAIL",
            checks=checks,
            context=self._context(),
        )
