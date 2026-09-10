"""Validate that an optimization proposal passed the RiskEngine gate."""
from __future__ import annotations

from typing import Any, Mapping

from ..pipeline import govern_proposal
from ..service import optimize_and_govern


def run(snapshot: Any, method: str = "hrp", **kwargs: Any) -> dict[str, Any]:
    return optimize_and_govern(snapshot, method, **kwargs)


def of_proposal(
    snapshot: Any,
    weights: Mapping[str, float],
    *,
    method: str,
    optimization: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    return govern_proposal(snapshot, weights, method=method, optimization=optimization, **kwargs)
