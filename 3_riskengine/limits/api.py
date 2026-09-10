"""Limit checks: weight gates (Wave 5) and portfolio Limit Engine (Wave 6)."""
from __future__ import annotations

from typing import Any, Mapping

from ..adapters.riskfolio.optimizer import (
    DEFAULT_CONSTRAINTS,
    apply_constraints,
    covariance_risk_contribution,
    turnover,
)
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .engine import evaluate as evaluate_snapshot
from .states import STATES


class LimitsAPI:
    def __init__(self, bound: Any | None = None):
        self._bound = bound

    def catalog(self) -> dict[str, Any]:
        from .policy import DEFAULT_SPECS, LIMIT_IDS, spec_as_dict

        return {
            "engine": RISKENGINE_NAME,
            "engine_version": RISKENGINE_VERSION,
            "limit_ids": list(LIMIT_IDS),
            "states": list(STATES),
            "defaults": [spec_as_dict(spec) for spec in DEFAULT_SPECS],
        }

    def evaluate(
        self,
        snapshot: Any | None = None,
        *,
        policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = snapshot
        if target is None and self._bound is not None:
            target = self._bound.snapshot
        if target is None:
            raise ValueError("LimitsAPI.evaluate requires a portfolio snapshot")
        return evaluate_snapshot(target, policy=policy)

    def check(
        self,
        weights: Mapping[str, float] | None = None,
        *,
        constraints: Mapping[str, Any] | None = None,
        current_weights: Mapping[str, float] | None = None,
        returns: Any | None = None,
        risk_budgets: Mapping[str, float] | None = None,
        snapshot: Any | None = None,
        policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "engine": RISKENGINE_NAME,
            "engine_version": RISKENGINE_VERSION,
            "is_trade_instruction": False,
        }
        weight_passed = True
        if weights is not None:
            weight_report = self._check_weights(
                weights,
                constraints=constraints,
                current_weights=current_weights,
                returns=returns,
                risk_budgets=risk_budgets,
            )
            payload.update(weight_report)
            weight_passed = bool(weight_report["passed"])

        target = snapshot
        if target is None and self._bound is not None:
            target = getattr(self._bound, "snapshot", None)
        if target is not None:
            portfolio = evaluate_snapshot(target, policy=policy)
            payload["portfolio"] = portfolio
            payload["state"] = portfolio["state"]
            payload["passed"] = weight_passed and bool(portfolio["passed"])
        elif weights is None:
            payload["status"] = "FAIL"
            payload["passed"] = False
            payload["checks"] = []
        return payload

    def _check_weights(
        self,
        weights: Mapping[str, float],
        *,
        constraints: Mapping[str, Any] | None = None,
        current_weights: Mapping[str, float] | None = None,
        returns: Any | None = None,
        risk_budgets: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        cfg = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
        lo = float(cfg["min_weight"])
        hi = min(float(cfg["max_weight"]), float(cfg["max_name_weight"]))
        total = float(sum(weights.values()))
        checks: list[dict[str, Any]] = []

        checks.append(
            {
                "name": "weights_sum_to_one",
                "passed": abs(total - 1.0) < 1e-6,
                "value": total,
            }
        )
        breaches = [k for k, v in weights.items() if v < lo - 1e-9 or v > hi + 1e-9]
        checks.append(
            {
                "name": "weight_bounds",
                "passed": not breaches,
                "value": {"min": lo, "max": hi, "breaches": breaches},
            }
        )
        if cfg.get("long_only", True):
            shorts = [k for k, v in weights.items() if v < -1e-9]
            checks.append({"name": "long_only", "passed": not shorts, "value": shorts})

        cash = str(cfg.get("cash_asset") or "CASH")
        min_liq = float(cfg.get("min_liquidity_pct") or 0.0)
        cash_w = float(weights.get(cash, 0.0))
        checks.append(
            {
                "name": "min_liquidity",
                "passed": cash_w + 1e-9 >= min_liq,
                "value": {"cash": cash_w, "floor": min_liq},
            }
        )

        turned = turnover(weights, current_weights or weights)
        cap = float(cfg.get("max_turnover") or 1.0)
        checks.append(
            {
                "name": "max_turnover",
                "passed": turned <= cap + 1e-9,
                "value": {"turnover": turned, "cap": cap},
            }
        )

        if returns is not None and risk_budgets:
            contrib = covariance_risk_contribution(weights, returns)
            drift = {
                k: abs(float(contrib.get(k, 0.0)) - float(risk_budgets.get(k, 0.0)))
                for k in set(contrib) | set(risk_budgets)
            }
            max_drift = max(drift.values()) if drift else 0.0
            checks.append(
                {
                    "name": "risk_budget",
                    "passed": max_drift < 0.15,
                    "value": {"max_abs_drift": max_drift, "contribution": contrib},
                }
            )

        passed = all(item["passed"] for item in checks)
        return {
            "status": "PASS" if passed else "BREACH",
            "passed": passed,
            "checks": checks,
        }

    def enforce(
        self,
        weights: Mapping[str, float],
        *,
        constraints: Mapping[str, Any] | None = None,
        current_weights: Mapping[str, float] | None = None,
    ) -> dict[str, float]:
        return apply_constraints(weights, constraints, current_weights=current_weights)


def check(
    weights: Mapping[str, float] | None = None,
    *,
    constraints: Mapping[str, Any] | None = None,
    current_weights: Mapping[str, float] | None = None,
    returns: Any | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    snapshot: Any | None = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return LimitsAPI().check(
        weights,
        constraints=constraints,
        current_weights=current_weights,
        returns=returns,
        risk_budgets=risk_budgets,
        snapshot=snapshot,
        policy=policy,
    )


def evaluate(snapshot: Any, *, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return evaluate_snapshot(snapshot, policy=policy)


def catalog() -> dict[str, Any]:
    return LimitsAPI().catalog()
