"""Domain models for the standalone FinancePy risk-testing module."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RiskFactorType(str, Enum):
    """Risk-factor families available to revaluation analytics."""

    RATE = "RATE"
    FX = "FX"
    VOLATILITY = "VOLATILITY"
    EQUITY = "EQUITY"
    CREDIT_SPREAD = "CREDIT_SPREAD"


class ShockMode(str, Enum):
    """Shock application modes."""

    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


@dataclass(frozen=True)
class Shock:
    """One auditable market-factor shock."""

    factor_type: RiskFactorType
    value: float
    mode: ShockMode
    tenor: str | None = None
    currency: str | None = None
    label: str = ""


@dataclass(frozen=True)
class Scenario:
    """A named set of simultaneous shocks."""

    scenario_id: str
    name: str
    category: str
    shocks: tuple[Shock, ...]
    description: str


@dataclass
class Position:
    """Normalized position loaded from existing ARISK holding tables."""

    security_code: str
    security_name: str
    asset_class: str
    currency: str
    market_value: float
    market_value_base: float
    duration: float = 0.0
    convexity: float = 0.0
    ytm: float = 0.0
    coupon_rate: float = 0.0
    maturity_date: date | None = None
    fx_rate: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioSnapshot:
    """Shared input snapshot for every analytic in one run."""

    fund_id: str
    as_of_date: date
    reporting_currency: str
    net_asset: float
    positions: list[Position]
    nav_returns: list[tuple[date, float]]
    data_quality: dict[str, Any]
