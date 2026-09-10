"""Liquidity floor on cash-like weight."""
from __future__ import annotations

from typing import Mapping

from ..constraints import apply as apply_constraints


def enforce(weights: Mapping[str, float], min_liquidity_pct: float, cash_asset: str = "CASH") -> dict[str, float]:
    return apply_constraints(
        weights,
        {"min_liquidity_pct": min_liquidity_pct, "cash_asset": cash_asset},
    )
