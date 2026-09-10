"""Unified RiskEngine contracts.

Calculation DTOs only. Portfolio, Position and market history continue to be
loaded from ``fsi.balance_*`` / ``fsi.mktdata_*``. This module does not create
a second master-data store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any


class ProductKind(str, Enum):
    EQUITY = "EQUITY"
    BOND = "BOND"
    MMF = "MMF"
    DEPOSIT = "DEPOSIT"
    CD = "CD"
    REPO = "REPO"
    FX = "FX"
    FX_FORWARD = "FX_FORWARD"
    FX_OPTION = "FX_OPTION"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    IRS = "IRS"
    SWAP = "SWAP"
    SWAPTION = "SWAPTION"
    CDS = "CDS"
    FUND = "FUND"
    ETF = "ETF"
    CASH = "CASH"
    STRUCTURED = "STRUCTURED"


class PortfolioKind(str, Enum):
    LIVE = "LIVE"
    SIMULATION = "SIMULATION"
    MODEL = "MODEL"
    BENCHMARK = "BENCHMARK"


class AnalyticKind(str, Enum):
    PRICE = "PRICE"
    GREEKS = "GREEKS"
    SENSITIVITY = "SENSITIVITY"
    CASHFLOW = "CASHFLOW"
    VAR = "VAR"
    CVAR = "CVAR"
    ES = "ES"
    OPTIMIZE = "OPTIMIZE"
    XVA = "XVA"
    EXPOSURE = "EXPOSURE"
    STRESS = "STRESS"
    LIQUIDITY = "LIQUIDITY"
    SCENARIO = "SCENARIO"
    REVERSE_STRESS = "REVERSE_STRESS"
    TAIL_RISK = "TAIL_RISK"
    KRD = "KRD"
    PNL_EXPLAIN = "PNL_EXPLAIN"
    HISTORICAL_BACKTEST = "HISTORICAL_BACKTEST"
    VAR_BACKTEST = "VAR_BACKTEST"


class RiskFactorType(str, Enum):
    RATE = "RATE"
    FX = "FX"
    VOLATILITY = "VOLATILITY"
    EQUITY = "EQUITY"
    CREDIT_SPREAD = "CREDIT_SPREAD"


class ShockMode(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


class ViewMode(str, Enum):
    PRODUCT = "PRODUCT"
    LOOK_THROUGH = "LOOK_THROUGH"


RESULT_LINEAGE_KEYS: tuple[str, ...] = (
    "portfolio_id",
    "position_id",
    "instrument_id",
    "trade_id",
    "valuation_date",
    "market_data_date",
    "calculation_time",
    "engine",
    "engine_version",
    "model",
    "model_version",
    "parameters",
    "assumptions",
    "data_quality",
    "result",
    "validation_status",
)


@dataclass(frozen=True)
class RiskFactor:
    factor_type: RiskFactorType
    tenor: str | None = None
    currency: str | None = None
    label: str = ""


@dataclass(frozen=True)
class Model:
    """Financial-mathematics model identity. Not a portfolio or governance object."""

    name: str
    family: str
    version: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Instrument:
    """Contract specification. Distinct from Trade and Position."""

    instrument_id: str
    asset_class: str
    currency: str
    name: str = ""
    product_kind: ProductKind | str = ProductKind.CASH
    maturity_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Product:
    """Product view: Product + Market + Model = Valuation."""

    kind: ProductKind
    instrument: Instrument
    currency: str = ""
    quantity: float = 0.0
    market_value: float = 0.0
    market_value_base: float = 0.0
    fx_rate: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.currency:
            self.currency = self.instrument.currency

    def value(self, market: "Market", model: Model | None = None) -> float:
        """Book value in reporting currency. Families may override (e.g. curve PV)."""

        del model
        if self.market_value_base:
            return float(self.market_value_base)
        quoted = None
        fx = float(self.fx_rate or 1.0)
        if market is not None:
            quoted = market.prices.get(self.instrument.instrument_id)
            fx = float(market.fx.get(self.currency, fx) or 1.0)
        if quoted is not None and self.quantity:
            return float(quoted) * float(self.quantity) * fx
        if quoted is not None:
            return float(quoted) * fx
        return 0.0

    def cashflows(self, market: "Market", model: Model | None = None) -> list[dict[str, Any]]:
        del market, model
        return []

    def sensitivity(self, market: "Market", shocks: tuple["Shock", ...] = ()) -> dict[str, Any]:
        base = self.value(market)
        return {"base_pv": base, "shocked_pv": base, "pnl": 0.0, "shocks": len(shocks)}


@dataclass
class Market:
    """Canonical market objects for one valuation date (curves, spots, vols)."""

    valuation_date: date
    prices: dict[str, float] = field(default_factory=dict)
    fx: dict[str, float] = field(default_factory=dict)
    curves: dict[str, Any] = field(default_factory=dict)
    credit_curves: dict[str, Any] = field(default_factory=dict)
    volatility: dict[str, Any] = field(default_factory=dict)
    macro: dict[str, Any] = field(default_factory=dict)

    def discount_factor(self, zero_rate: float, years: float) -> float:
        fn = self.curves.get("discount_factor")
        if callable(fn):
            return float(fn(zero_rate, years))
        import math

        return float(math.exp(-max(float(zero_rate), -0.05) * max(float(years), 0.0)))

    def shocked_discount_factor(self, zero_rate: float, shock: float, years: float) -> float:
        fn = self.curves.get("shocked_discount_factor")
        if callable(fn):
            return float(fn(zero_rate, shock, years))
        return self.discount_factor(float(zero_rate) + float(shock), years)


@dataclass
class Trade:
    """Investment/trading view: Instrument + counterparty + CSA + terms."""

    trade_id: str
    instrument: Instrument
    counterparty: str = ""
    portfolio_id: str = ""
    quantity: float = 0.0
    netting_set: str | None = None
    collateral_agreement: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    """Booked holding. Points at an Instrument; may reference a Trade."""

    instrument: Instrument
    security_code: str
    quantity_value: float
    market_value: float
    market_value_base: float
    duration: float = 0.0
    convexity: float = 0.0
    ytm: float = 0.0
    coupon_rate: float = 0.0
    fx_rate: float = 1.0
    trade_id: str = ""
    portfolio_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Portfolio:
    """Unified book: LIVE / SIMULATION / MODEL / BENCHMARK."""

    portfolio_id: str
    as_of_date: date
    reporting_currency: str
    net_asset: float
    positions: list[Position]
    kind: PortfolioKind = PortfolioKind.LIVE
    trades: list[Trade] = field(default_factory=list)


@dataclass
class MarketSnapshot:
    """Dated market + NAV history used with an ARISK portfolio snapshot."""

    as_of_date: date
    reporting_currency: str
    nav_returns: list[tuple[date, float]] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    market: Market | None = None


@dataclass
class ValuationContext:
    valuation_date: date
    market_data_date: date
    curve: str
    model: str
    assumption: tuple[str, ...]
    engine_version: str
    engine: str = "ARISK RiskEngine"
    model_version: str = ""
    portfolio_id: str = ""
    position_id: str = ""
    instrument_id: str = ""
    trade_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    scenario_id: str
    name: str
    category: str
    shocks: tuple["Shock", ...]
    description: str = ""


@dataclass(frozen=True)
class Shock:
    factor_type: RiskFactorType
    value: float
    mode: ShockMode = ShockMode.ABSOLUTE
    tenor: str | None = None
    currency: str | None = None
    label: str = ""


@dataclass
class ValuationResult:
    base_pv: float
    shocked_pv: float
    pnl: float
    pnl_pct_nav: float | None
    trade_values: list[dict[str, Any]]
    context: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskResult:
    analytic: str
    payload: dict[str, Any]
    context: dict[str, Any]
    validation_status: str = "UNVALIDATED"


@dataclass
class StressResult:
    analytic: str
    payload: dict[str, Any]
    context: dict[str, Any]


@dataclass
class ValidationResult:
    status: str
    checks: list[dict[str, Any]]
    context: dict[str, Any]


def lineage_context(
    *,
    valuation_date: date,
    market_data_date: date | None = None,
    curve: str = "FinancePy FlatDiscountCurve (DiscountCurveFlat compatible)",
    model: str = "ARISK unified revaluation",
    engine_version: str,
    engine: str = "ARISK RiskEngine",
    assumptions: list[str] | tuple[str, ...] | None = None,
    parameters: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
    portfolio_id: str = "",
    position_id: str = "",
    instrument_id: str = "",
    trade_id: str = "",
    calculation_time: datetime | None = None,
    model_version: str | None = None,
    result: Any = None,
    validation_status: str = "UNVALIDATED",
) -> dict[str, Any]:
    """Fields required on every valuation / risk report."""

    stamp = calculation_time or datetime.now(UTC)
    return {
        "portfolio_id": portfolio_id,
        "position_id": position_id,
        "instrument_id": instrument_id,
        "trade_id": trade_id,
        "valuation_date": valuation_date.isoformat(),
        "market_data_date": (market_data_date or valuation_date).isoformat(),
        "calculation_time": stamp.isoformat(),
        "engine": engine,
        "engine_version": engine_version,
        "model": model,
        "model_version": model_version or engine_version,
        "curve": curve,
        "parameters": parameters or {},
        "assumptions": list(assumptions or ()),
        "assumption": list(assumptions or ()),
        "data_quality": data_quality or {},
        "result": result,
        "validation_status": validation_status,
    }
