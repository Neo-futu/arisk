"""Risk Limits — always the shared Limit Engine."""
from __future__ import annotations

from typing import Any, Mapping

from ..service import evaluate_limits


def run(snapshot: Any, *, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return evaluate_limits(snapshot, policy=policy)
