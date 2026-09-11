"""Limit states for the unified Limit Engine."""
from __future__ import annotations

from enum import Enum

STATES = ("GREEN", "WARNING", "BREACH", "HARD_BREACH")


class LimitState(str, Enum):
    GREEN = "GREEN"
    WARNING = "WARNING"
    BREACH = "BREACH"
    HARD_BREACH = "HARD_BREACH"


RANK = {
    LimitState.GREEN: 0,
    LimitState.WARNING: 1,
    LimitState.BREACH: 2,
    LimitState.HARD_BREACH: 3,
}


def worst(*states: LimitState | str) -> LimitState:
    ranked: list[LimitState] = []
    for item in states:
        ranked.append(item if isinstance(item, LimitState) else LimitState(item))
    return max(ranked, key=lambda item: RANK[item]) if ranked else LimitState.GREEN


def classify(utilization: float, *, warning: float = 0.8, hard: float = 1.1) -> LimitState:
    """Map utilization onto a state.

    At-limit (utilization == 1.0) is still inside the published limit (WARNING
    once the warning band is reached). Exceeding the limit is BREACH; reaching
    the hard multiple is HARD_BREACH.
    """

    if utilization >= hard:
        return LimitState.HARD_BREACH
    if utilization > 1.0:
        return LimitState.BREACH
    if utilization >= warning:
        return LimitState.WARNING
    return LimitState.GREEN
