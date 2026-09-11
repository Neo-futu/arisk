"""Portfolio optimization domain catalog."""
from __future__ import annotations

OPTIMIZERS: tuple[str, ...] = (
    "construction",
    "saa",
    "taa",
    "risk_budget",
    "risk_parity",
    "black_litterman",
    "hrp",
    "herc",
    "cvar",
)

SUPPORT: tuple[str, ...] = (
    "constraints",
    "liquidity",
    "turnover",
    "simulation",
    "validation",
)

MODULES: tuple[str, ...] = OPTIMIZERS + SUPPORT

GATE = (
    "optimization",
    "riskengine",
    "valuation",
    "investment_risk",
    "risk_testing",
    "limits",
)
