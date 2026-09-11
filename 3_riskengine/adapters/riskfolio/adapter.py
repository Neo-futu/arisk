"""Riskfolio-Lib adapter. Vendor import is isolated here."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..vendor import VendorProbe, probe_module
from .optimizer import (
    OPTIMIZATION_METHODS,
    covariance_risk_contribution,
    fallback_optimize,
    try_riskfolio_optimize,
    turnover,
)


class RiskfolioAdapter:
    """Portfolio risk-measure adapter. Falls back to RiskEngine statistics when absent."""

    name = "riskfolio"

    def __init__(self) -> None:
        self._probe, self._module = probe_module("riskfolio")

    def initialize(self) -> VendorProbe:
        return self._probe

    @property
    def available(self) -> bool:
        return self._probe.available

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self._probe.version,
            "error": self._probe.error,
            "role": "VaR/CVaR, portfolio risk measures, and Riskfolio-Lib optimization (HRP/HERC/CVaR/RP/BL)",
        }

    def optimize(
        self,
        returns: pd.DataFrame,
        method: str,
        *,
        constraints: Mapping[str, Any] | None = None,
        current_weights: Mapping[str, float] | None = None,
        views: Mapping[str, float] | None = None,
        risk_budgets: Mapping[str, float] | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        """Run a named optimizer. Riskfolio-Lib when installed, else deterministic fallback."""

        key = method.strip().lower()
        if key not in OPTIMIZATION_METHODS:
            raise ValueError(f"Unsupported optimization method: {method}")
        engine_name = "riskfolio" if self.available else "riskengine_fallback"
        weights = None
        if self.available:
            try:
                weights = try_riskfolio_optimize(
                    self._module,
                    returns,
                    key,
                    constraints=constraints,
                    views=views,
                    risk_budgets=risk_budgets,
                )
            except Exception:  # noqa: BLE001 — published numbers stay on the fallback
                engine_name = "riskengine_fallback"
                weights = None
        if weights is None:
            weights = fallback_optimize(
                returns,
                key,
                constraints=constraints,
                current_weights=current_weights,
                views=views,
                risk_budgets=risk_budgets,
                confidence=confidence,
            )
            if engine_name == "riskfolio":
                engine_name = "riskengine_fallback"
        contributions = covariance_risk_contribution(weights, returns)
        return {
            "method": key,
            "weights": weights,
            "risk_contribution": contributions,
            "engine": engine_name,
            "available": self.available,
            "is_trade_instruction": False,
            "status": "PROPOSAL",
        }

    def risk_contribution(
        self,
        weights: Mapping[str, float],
        returns: pd.DataFrame,
        *,
        rm: str = "MV",
        confidence: float = 0.95,
    ) -> dict[str, float]:
        """Euler risk contribution. Riskfolio ``Risk_Contribution`` when installed."""

        if returns is None or getattr(returns, "empty", False) or returns.shape[1] == 0:
            return {}
        if self.available:
            try:
                aligned = pd.Series({str(col): float(weights.get(col, 0.0)) for col in returns.columns})
                total = float(aligned.sum())
                if total <= 0:
                    aligned = pd.Series(1.0 / max(len(aligned), 1), index=aligned.index)
                else:
                    aligned = aligned / total
                raw = self._module.Risk_Contribution(
                    aligned,
                    returns,
                    rm=rm,
                    alpha=max(1.0 - float(confidence), 1e-6),
                )
                values = np.asarray(raw, dtype=float).reshape(-1)
                denom = float(values.sum())
                if abs(denom) > 1e-18 and values.size == len(returns.columns):
                    return {str(col): float(values[i] / denom) for i, col in enumerate(returns.columns)}
            except Exception:  # noqa: BLE001 — published numbers stay on covariance path
                pass
        return covariance_risk_contribution(weights, returns)

    def turnover(self, new_weights: Mapping[str, float], old_weights: Mapping[str, float]) -> float:
        return turnover(new_weights, old_weights)

    def historical_var_cvar(
        self,
        returns: list[float] | np.ndarray,
        confidence: float = 0.99,
    ) -> dict[str, Any]:
        """Return historical VaR/CVaR. Uses Riskfolio when installed, else NumPy."""

        sample = np.asarray(returns, dtype=float)
        alpha = (1.0 - confidence) * 100.0
        if sample.size == 0:
            return {
                "engine": "riskfolio" if self.available else "riskengine_numpy",
                "available": self.available,
                "status": "INSUFFICIENT_DATA",
                "var": None,
                "cvar": None,
            }
        var_return = float(np.percentile(sample, alpha))
        tail = sample[sample <= var_return]
        cvar_return = float(np.mean(tail)) if tail.size else var_return
        engine_name = "riskfolio" if self.available else "riskengine_numpy"
        if self.available:
            try:
                var_return, cvar_return = self._riskfolio_var_cvar(sample, confidence, var_return, cvar_return)
                engine_name = "riskfolio"
            except Exception:  # noqa: BLE001 — keep published RiskEngine numbers if vendor call fails
                engine_name = "riskengine_numpy_fallback"
        return {
            "engine": engine_name,
            "available": self.available,
            "status": "OK",
            "var": var_return,
            "cvar": cvar_return,
            "confidence": confidence,
            "observations": int(sample.size),
        }

    def _riskfolio_var_cvar(
        self,
        sample: np.ndarray,
        confidence: float,
        fallback_var: float,
        fallback_cvar: float,
    ) -> tuple[float, float]:
        """Historical VaR/CVaR via Riskfolio ``VaR_Hist`` / ``CVaR_Hist``.

        Riskfolio reports positive loss. This adapter publishes the left-tail
        return (negative on a loss day) so callers can do ``abs(r) × NAV``.
        """

        if sample.size < 3:
            return fallback_var, fallback_cvar
        alpha = max(1.0 - float(confidence), 1e-6)
        var_fn = getattr(self._module, "VaR_Hist", None)
        cvar_fn = getattr(self._module, "CVaR_Hist", None)
        if not callable(var_fn) or not callable(cvar_fn):
            return fallback_var, fallback_cvar
        var_loss = float(var_fn(sample, alpha=alpha))
        cvar_loss = float(cvar_fn(sample, alpha=alpha))
        return -var_loss, -cvar_loss
