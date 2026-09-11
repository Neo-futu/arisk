"""Weight / turnover / liquidity constraint enforcement."""
from __future__ import annotations

from typing import Any, Mapping

from importlib import import_module

_opt = import_module("3_riskengine.adapters.riskfolio.optimizer")
_limits = import_module("3_riskengine.limits")


def apply(weights: Mapping[str, float], constraints: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, float]:
    return _opt.apply_constraints(weights, constraints, current_weights=kwargs.get("current_weights"))


def check(weights: Mapping[str, float], **kwargs: Any) -> dict[str, Any]:
    return _limits.check(weights, **kwargs)
