"""FinancePy-powered revaluation — compatibility facade over 3_riskengine kernel."""
from __future__ import annotations

from typing import Any, Iterable

from importlib import import_module

from .models import PortfolioSnapshot, Scenario, Shock


class ProfessionalRiskEngine:
    """Run ORE-style risk workflows on an existing ARISK portfolio snapshot.

    Calculation lives in ``3_riskengine.core.kernel``. This class keeps the
    historical import path used by Risk Testing analytics and HTTP.
    """

    engine_name = "FinancePy Professional Risk Engine"

    def __init__(self, snapshot: PortfolioSnapshot):
        engine = import_module("3_riskengine.core.engine").RiskEngine()
        self.snapshot = snapshot
        self._kernel = engine.bind(snapshot).kernel()
        self.financepy = self._kernel.financepy

    def value(self, shocks: Iterable[Shock] = ()) -> dict[str, Any]:
        return self._kernel.value(shocks)

    def sensitivity(self, shocks: Iterable[Shock]) -> dict[str, Any]:
        return self._kernel.sensitivity(shocks)

    def scenario(self, scenario: Scenario) -> dict[str, Any]:
        return self._kernel.scenario(scenario)

    def reverse_stress(
        self,
        scenario: Scenario,
        target_loss_pct_nav: float,
        max_scale: float = 20.0,
    ) -> dict[str, Any]:
        return self._kernel.reverse_stress(scenario, target_loss_pct_nav, max_scale)

    def tail_risk(self, sigma_levels: Iterable[float], capital_buffer: float) -> dict[str, Any]:
        return self._kernel.tail_risk(sigma_levels, capital_buffer)

    def krd(self, bump_bps: float = 1.0) -> dict[str, Any]:
        return self._kernel.krd(bump_bps)

    def var_backtest(self, confidence: float = 0.99, window: int = 60) -> dict[str, Any]:
        return self._kernel.var_backtest(confidence, window)

    def xva(
        self,
        counterparty_hazard: float,
        own_hazard: float,
        recovery_rate: float,
        funding_spread: float,
        initial_margin_pct: float,
        mva_funding_spread: float,
    ) -> dict[str, Any]:
        return self._kernel.xva(
            counterparty_hazard,
            own_hazard,
            recovery_rate,
            funding_spread,
            initial_margin_pct,
            mva_funding_spread,
        )

    def pnl_explain(self, previous: PortfolioSnapshot) -> dict[str, Any]:
        return self._kernel.pnl_explain(previous)
