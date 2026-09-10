"""Portfolio aggregation API: Portfolio Risk, Fund Risk, VaR/CVaR/RC/optimize."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.contracts import ViewMode
from ..core.lineage import RISKENGINE_VERSION
from .aggregate import aggregate
from .measures import fund_risk, optimize_book, portfolio_risk


class PortfolioAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def aggregate(
        self,
        view: ViewMode | str = ViewMode.LOOK_THROUGH,
        shocks: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        report = aggregate(self._bound, view=view, shocks=shocks)
        report.setdefault("engine_version", RISKENGINE_VERSION)
        return report

    def risk(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        """Look-through Portfolio Risk."""

        return portfolio_risk(self._bound, confidence=confidence, returns=returns)

    def fund_risk(self, *, confidence: float = 0.99) -> dict[str, Any]:
        """Share-class Fund Risk (PRODUCT view + NAV history)."""

        return fund_risk(self._bound, confidence=confidence)

    def var(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        pack = self.fund_risk(confidence=confidence) if scope == "fund" else self.risk(confidence=confidence)
        return {
            "analytic": "VAR",
            "scope": pack["scope"],
            **pack["var_cvar"],
            "nav": pack["nav"],
        }

    def cvar(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        pack = self.var(confidence=confidence, scope=scope)
        pack["analytic"] = "CVAR"
        return pack

    def contribution(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        pack = self.risk(confidence=confidence, returns=returns)
        return {
            "analytic": "RISK_CONTRIBUTION",
            "scope": "PORTFOLIO",
            **pack["risk_contribution"],
            "weights": {row["security_code"]: row["weight"] for row in pack["positions"]},
            "engine_version": RISKENGINE_VERSION,
        }

    def optimize(
        self,
        method: str,
        *,
        returns: Any | None = None,
        constraints: Mapping[str, Any] | None = None,
        views: Mapping[str, float] | None = None,
        risk_budgets: Mapping[str, float] | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        return optimize_book(
            self._bound,
            method,
            returns=returns,
            constraints=constraints,
            views=views,
            risk_budgets=risk_budgets,
            confidence=confidence,
        )
