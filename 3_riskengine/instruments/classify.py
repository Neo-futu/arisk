"""Map platform holdings (fsi.balance_*) onto RiskEngine instrument families.

Does not create a second instrument master. Identifiers stay on the snapshot.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..core.contracts import ProductKind

FIXED_INCOME = frozenset({"BOND", "CD", "DEPOSIT"})
EQUITY_LIKE = frozenset({"EQUITY"})
FUND_LIKE = frozenset({"FUND", "ETF"})
MMF_LIKE = frozenset({"MMF"})
CASH_LIKE = frozenset({"CASH", "UNMAPPED_CASH"})

KRD_BUCKETS: tuple[tuple[str, float], ...] = (
    ("1M", 1 / 12),
    ("3M", 0.25),
    ("6M", 0.5),
    ("1Y", 1.0),
    ("2Y", 2.0),
    ("3Y", 3.0),
    ("5Y", 5.0),
    ("10Y", 10.0),
    ("20Y+", 20.0),
)

_KIND_BY_ASSET = {
    "BOND": ProductKind.BOND,
    "CD": ProductKind.CD,
    "DEPOSIT": ProductKind.DEPOSIT,
    "EQUITY": ProductKind.EQUITY,
    "CASH": ProductKind.CASH,
    "UNMAPPED_CASH": ProductKind.CASH,
    "MMF": ProductKind.MMF,
    "ETF": ProductKind.ETF,
    "FUND": ProductKind.FUND,
    "FX": ProductKind.FX,
    "FX_SPOT": ProductKind.FX,
    "FX_FORWARD": ProductKind.FX_FORWARD,
    "FXFORWARD": ProductKind.FX_FORWARD,
    "FX_OPTION": ProductKind.FX_OPTION,
    "FXOPTION": ProductKind.FX_OPTION,
    "FUTURE": ProductKind.FUTURE,
    "FUTURES": ProductKind.FUTURE,
    "OPTION": ProductKind.OPTION,
    "EQ_OPTION": ProductKind.OPTION,
    "EQUITY_OPTION": ProductKind.OPTION,
    "IRS": ProductKind.IRS,
    "SWAP": ProductKind.SWAP,
    "SWAPTION": ProductKind.SWAPTION,
    "CDS": ProductKind.CDS,
    "CREDIT_DEFAULT_SWAP": ProductKind.CDS,
}


def years_to_maturity(position: Any, as_of: date) -> float:
    """Horizon used for FinancePy discounting: maturity if present, else duration."""

    years = float(getattr(position, "duration", 0.0) or 0.0)
    maturity = getattr(position, "maturity_date", None)
    if maturity is not None:
        years = max((maturity - as_of).days / 365.0, 1 / 365)
    return max(years, 0.0)


def days_to_maturity(position: Any, as_of: date) -> float:
    maturity = getattr(position, "maturity_date", None)
    if maturity is not None:
        return float(max((maturity - as_of).days, 0))
    return max(float(getattr(position, "duration", 0.0) or 0.0) * 365.0, 0.0)


def krd_bucket(position: Any, as_of: date) -> str:
    years = float(getattr(position, "duration", 0.0) or 0.0)
    maturity = getattr(position, "maturity_date", None)
    if maturity is not None:
        years = max((maturity - as_of).days / 365.0, years)
    for label, boundary in KRD_BUCKETS:
        if years <= boundary:
            return label
    return "20Y+"


def annual_rate(position: Any) -> float:
    ytm = float(getattr(position, "ytm", 0.0) or 0.0)
    if abs(ytm) >= 1.0:
        ytm /= 100.0
    return ytm


def coupon_rate(position: Any) -> float:
    coupon = float(getattr(position, "coupon_rate", 0.0) or 0.0)
    if abs(coupon) >= 1.0:
        coupon /= 100.0
    return coupon


def asset_class(position: Any) -> str:
    return str(getattr(position, "asset_class", "") or "OTHER")


def is_fixed_income(position: Any) -> bool:
    return asset_class(position) in FIXED_INCOME


def is_equity_like(position: Any) -> bool:
    return asset_class(position) in EQUITY_LIKE


def is_fund_like(position: Any) -> bool:
    return product_kind_of(position) in {ProductKind.FUND, ProductKind.ETF, ProductKind.MMF}


def is_mmf(position: Any) -> bool:
    return product_kind_of(position) is ProductKind.MMF


def is_cash_like(position: Any) -> bool:
    return asset_class(position) in CASH_LIKE


def product_kind_of(position: Any) -> ProductKind:
    klass = asset_class(position)
    if klass == "FUND":
        hint = " ".join(
            str(item or "")
            for item in (
                (getattr(position, "metadata", None) or {}).get("fund_type"),
                (getattr(position, "metadata", None) or {}).get("issuer"),
                getattr(position, "security_name", ""),
            )
        ).upper()
        if "MMF" in hint or "MONEY MARKET" in hint or "貨幣市場" in hint:
            return ProductKind.MMF
        return ProductKind.FUND
    return _KIND_BY_ASSET.get(klass, ProductKind.CASH)


def factor_family(position: Any, reporting_currency: str) -> str:
    kind = product_kind_of(position)
    if kind in {ProductKind.BOND, ProductKind.CD, ProductKind.DEPOSIT}:
        family = "RATE_CREDIT"
    elif kind is ProductKind.EQUITY:
        family = "EQUITY"
    elif kind is ProductKind.MMF:
        family = "MMF"
    elif kind in {ProductKind.FUND, ProductKind.ETF}:
        family = "FUND"
    elif kind is ProductKind.CASH:
        family = "CASH"
    elif kind in {ProductKind.FX, ProductKind.FX_FORWARD, ProductKind.FX_OPTION}:
        family = "FX"
    elif kind in {ProductKind.IRS, ProductKind.SWAP, ProductKind.SWAPTION, ProductKind.FUTURE}:
        family = "RATE"
    elif kind is ProductKind.OPTION:
        family = "EQUITY"
    elif kind is ProductKind.CDS:
        family = "CREDIT"
    else:
        family = kind.value
    currency = str(getattr(position, "currency", "") or reporting_currency)
    if currency != reporting_currency:
        return f"{family}+FX"
    return family


def issuer_name(position: Any) -> str:
    metadata = getattr(position, "metadata", None) or {}
    return str(
        metadata.get("issuer_name")
        or metadata.get("issuer")
        or getattr(position, "security_name", None)
        or getattr(position, "security_code", "UNKNOWN")
    )
