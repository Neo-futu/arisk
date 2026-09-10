"""Implied asset-return panels for Riskfolio when only fund NAV history exists."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..market.snapshot import nav_returns

# Asset-class loadings onto the fund NAV series. Cash is a near-zero residual.
_KIND_BETA: dict[str, float] = {
    "EQUITY": 1.00,
    "OPTION": 1.20,
    "FUTURE": 1.10,
    "ETF": 1.00,
    "FUND": 0.80,
    "BOND": 0.20,
    "CD": 0.08,
    "DEPOSIT": 0.05,
    "MMF": 0.04,
    "CASH": 0.00,
    "FX": 0.50,
    "FX_FORWARD": 0.45,
    "FX_OPTION": 0.70,
    "IRS": 0.25,
    "SWAP": 0.25,
    "SWAPTION": 0.40,
    "CDS": 0.35,
    "REPO": 0.05,
    "STRUCTURED": 0.50,
}


def implied_asset_returns(snapshot: Any, positions: list[Mapping[str, Any]]) -> pd.DataFrame:
    """Map one NAV series onto product columns with class betas + tiny residual."""

    nav = nav_returns(snapshot)
    if nav.size == 0 or not positions:
        return pd.DataFrame()
    time = np.arange(nav.size, dtype=float)
    data: dict[str, np.ndarray] = {}
    for index, row in enumerate(positions):
        code = str(row.get("security_code") or f"P{index}")
        beta = float(_KIND_BETA.get(str(row.get("asset_class") or ""), 0.30))
        residual = 1e-4 * np.sin((time + 1.0) * (index + 1.0))
        data[code] = beta * nav + residual
    return pd.DataFrame(data)


def weights_from_positions(positions: list[Mapping[str, Any]]) -> dict[str, float]:
    total = sum(abs(float(item.get("base_pv") or 0.0)) for item in positions)
    if total <= 0:
        n = max(len(positions), 1)
        return {str(item.get("security_code") or i): 1.0 / n for i, item in enumerate(positions)}
    return {str(item.get("security_code")): float(item.get("base_pv") or 0.0) / total for item in positions}
