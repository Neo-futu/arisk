"""Map fsi.balance_* snapshot rows onto Product objects.

Two views:
- PRODUCT: money-market books collapse to one MMF; mixed books stay as line products
- LOOK_THROUGH: holding-level Equity / Bond / MMF / Deposit / CD / Cash
"""
from __future__ import annotations

from typing import Any

from ..core.contracts import Instrument, Product, ProductKind, ViewMode
from ..instruments.classify import coupon_rate, issuer_name, product_kind_of
from .cash import Cash
from .credit import CreditDefaultSwap
from .equity import Equity
from .fixed_income import Bond, CertificateOfDeposit, Deposit, Repo
from .fx import FxForward, FxOption, FxSpot
from .futures import Future
from .money_market.fund import MoneyMarketFund, is_money_market_book
from .options import EquityOption
from .rates import InterestRateSwap, Swaption
from .structured import StructuredNote


def _instrument(position: Any, kind: ProductKind) -> Instrument:
    return Instrument(
        instrument_id=str(position.security_code),
        asset_class=str(position.asset_class),
        currency=str(position.currency),
        name=str(getattr(position, "security_name", "") or position.security_code),
        product_kind=kind,
        maturity_date=getattr(position, "maturity_date", None),
        metadata=dict(getattr(position, "metadata", None) or {}),
    )


def _common(position: Any) -> dict[str, Any]:
    market_value = float(position.market_value)
    return {
        "quantity": 1.0,
        "market_value": market_value,
        "market_value_base": float(position.market_value_base),
        "fx_rate": float(getattr(position, "fx_rate", 1.0) or 1.0),
        "metadata": dict(getattr(position, "metadata", None) or {}),
        "currency": str(position.currency),
    }


def _otc_fields(position: Any, common: dict[str, Any]) -> dict[str, Any]:
    meta = common["metadata"]
    return {
        "notional": float(meta.get("notional") or common["market_value_base"]),
        "strike": float(meta.get("strike") or 0.0),
        "volatility": float(meta.get("volatility") or 0.20),
        "option_type": str(meta.get("option_type") or "Call"),
        "exercise": str(meta.get("exercise") or "European"),
        "underlying": str(meta.get("underlying") or ""),
        "pair": str(meta.get("pair") or ""),
        "spot": float(meta.get("spot") or common["fx_rate"] or 0.0),
        "domestic_rate": float(meta.get("domestic_rate") or 0.03),
        "foreign_rate": float(meta.get("foreign_rate") or 0.03),
        "hazard_rate": float(meta.get("hazard_rate") or 0.01),
        "recovery_rate": float(meta.get("recovery_rate") or 0.40),
        "pay_fixed": bool(meta.get("pay_fixed", True)),
        "protection_seller": bool(meta.get("protection_seller", False)),
        "tenor_years": float(meta.get("tenor_years") or getattr(position, "duration", 0.0) or 5.0),
        "option_tenor_years": float(meta.get("option_tenor_years") or 1.0),
        "maturity_date": getattr(position, "maturity_date", None),
    }


def product_from_holding(position: Any) -> Product:
    kind = product_kind_of(position)
    instrument = _instrument(position, kind)
    common = _common(position)
    fi = {
        "duration": float(getattr(position, "duration", 0.0) or 0.0),
        "convexity": float(getattr(position, "convexity", 0.0) or 0.0),
        "ytm": float(getattr(position, "ytm", 0.0) or 0.0),
        "coupon_rate": coupon_rate(position),
        "maturity_date": getattr(position, "maturity_date", None),
    }
    otc = _otc_fields(position, common)
    if kind is ProductKind.BOND:
        return Bond(kind=kind, instrument=instrument, **common, **fi)
    if kind is ProductKind.DEPOSIT:
        return Deposit(kind=kind, instrument=instrument, **common, **fi)
    if kind is ProductKind.CD:
        return CertificateOfDeposit(kind=kind, instrument=instrument, **common, **fi)
    if kind is ProductKind.REPO:
        return Repo(
            kind=kind,
            instrument=instrument,
            **common,
            **fi,
            haircut=float(common["metadata"].get("haircut") or 0.0),
            repo_rate=float(common["metadata"].get("repo_rate") or fi.get("ytm") or 0.0),
        )
    if kind is ProductKind.EQUITY:
        return Equity(kind=kind, instrument=instrument, **common)
    if kind is ProductKind.MMF:
        return MoneyMarketFund(kind=kind, instrument=instrument, **common, nav=common["market_value_base"])
    if kind is ProductKind.FX:
        return FxSpot(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.FX_FORWARD:
        return FxForward(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.FX_OPTION:
        return FxOption(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.FUTURE:
        return Future(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.OPTION:
        return EquityOption(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.IRS:
        return InterestRateSwap(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.SWAP:
        return InterestRateSwap(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.SWAPTION:
        return Swaption(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.CDS:
        return CreditDefaultSwap(kind=kind, instrument=instrument, **common, **otc)
    if kind is ProductKind.STRUCTURED:
        return StructuredNote(kind=kind, instrument=instrument, **common, **otc)
    if kind in {ProductKind.FUND, ProductKind.ETF}:
        return Product(kind=kind, instrument=instrument, **common)
    return Cash(kind=ProductKind.CASH, instrument=instrument, **common)


def products_from_snapshot(
    snapshot: Any,
    view: ViewMode | str = ViewMode.PRODUCT,
) -> list[Product]:
    mode = ViewMode(str(getattr(view, "value", view)))
    lines = [product_from_holding(position) for position in snapshot.positions]
    if mode is ViewMode.LOOK_THROUGH:
        expanded: list[Product] = []
        for item in lines:
            if isinstance(item, MoneyMarketFund) and item.holdings:
                expanded.extend(item.look_through())
            else:
                expanded.append(item)
        return expanded
    if is_money_market_book(lines):
        header = Instrument(
            instrument_id=str(getattr(snapshot, "fund_id", "MMF")),
            asset_class="MMF",
            currency=str(snapshot.reporting_currency),
            name=str(getattr(snapshot, "fund_id", "MMF")),
            product_kind=ProductKind.MMF,
        )
        return [
            MoneyMarketFund(
                kind=ProductKind.MMF,
                instrument=header,
                quantity=1.0,
                currency=snapshot.reporting_currency,
                market_value=float(snapshot.net_asset),
                market_value_base=float(snapshot.net_asset),
                nav=float(snapshot.net_asset),
                holdings=lines,
                view=ViewMode.PRODUCT,
                metadata={"issuer": issuer_name(lines[0]) if lines else "MMF"},
            )
        ]
    return lines
