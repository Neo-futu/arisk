"""Bond / Deposit / CD. Discounting uses Market curve callables (FinancePy behind adapter)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..core.contracts import Market, Model, Product, ProductKind, Shock
from ..instruments.classify import annual_rate, coupon_rate, years_to_maturity
from ..instruments.shocks import applicable_shocks, reporting_currency


def _rate_shift(product: "FixedIncomeProduct", market: Market, shocks: tuple[Shock, ...]) -> float:
    shift = 0.0
    for shock in applicable_shocks(product, shocks, market):
        key = str(getattr(shock.factor_type, "value", shock.factor_type))
        if key in {"RATE", "CREDIT_SPREAD"}:
            shift += float(shock.value)
    return shift


def _fx_multiplier(product: Product, market: Market, shocks: tuple[Shock, ...]) -> float:
    reporting = reporting_currency(market, product)
    if product.currency == reporting:
        return 1.0
    fx_rel = 0.0
    for shock in applicable_shocks(product, shocks, market):
        key = str(getattr(shock.factor_type, "value", shock.factor_type))
        if key == "FX":
            fx_rel += float(shock.value)
    return 1.0 + fx_rel


def _reprice(product: "FixedIncomeProduct", market: Market, rate_shift: float) -> float:
    as_of = market.valuation_date if market is not None else date.min
    years = years_to_maturity(product, as_of) if as_of != date.min else max(product.duration, 0.0)
    rate = annual_rate(product)
    wrapped = market.curves.get("reprice_from_ytm") if market is not None else None
    if callable(wrapped):
        return float(wrapped(rate, years, product.market_value_base, rate_shift))
    base_df = market.discount_factor(rate, years) if market is not None else 1.0
    terminal = product.market_value_base / base_df if base_df else product.market_value_base
    shocked_df = (
        market.shocked_discount_factor(rate, rate_shift, years) if market is not None else base_df
    )
    return float(terminal * shocked_df)


@dataclass
class FixedIncomeProduct(Product):
    duration: float = 0.0
    convexity: float = 0.0
    ytm: float = 0.0
    coupon_rate: float = 0.0
    maturity_date: date | None = None

    def cashflows(self, market: Market, model: Model | None = None) -> list[dict[str, Any]]:
        del model
        as_of = market.valuation_date if market is not None else date.min
        years = years_to_maturity(self, as_of) if as_of != date.min else max(self.duration, 0.0)
        coupon = coupon_rate(self)
        return [
            {
                "type": "coupon",
                "rate": coupon,
                "amount": self.market_value_base * coupon * years,
            },
            {
                "type": "redemption",
                "years": years,
                "amount": self.market_value_base,
            },
        ]

    def value(self, market: Market, model: Model | None = None) -> float:
        del model
        if market is None:
            return float(self.market_value_base)
        return _reprice(self, market, 0.0)

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        base = self.value(market)
        shocked = _reprice(self, market, _rate_shift(self, market, shocks)) if market is not None else base
        shocked *= _fx_multiplier(self, market, shocks)
        return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}


@dataclass
class Bond(FixedIncomeProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.BOND
        super().__post_init__()


@dataclass
class Deposit(FixedIncomeProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.DEPOSIT
        super().__post_init__()


@dataclass
class CertificateOfDeposit(FixedIncomeProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.CD
        super().__post_init__()


@dataclass
class Repo(FixedIncomeProduct):
    """回购 / 逆回购。零冲击=账面；利率冲击走 FinancePy ``repo_carry`` 曲线再定价。"""

    haircut: float = 0.0
    repo_rate: float = 0.0

    def __post_init__(self) -> None:
        self.kind = ProductKind.REPO
        meta = dict(self.metadata or {})
        if not self.haircut:
            self.haircut = float(meta.get("haircut") or 0.0)
        if not self.repo_rate:
            self.repo_rate = float(meta.get("repo_rate") or self.ytm or 0.0)
        if abs(self.repo_rate) >= 1.0:
            self.repo_rate /= 100.0
        if self.repo_rate and not self.ytm:
            self.ytm = self.repo_rate
        super().__post_init__()

    def cashflows(self, market: Market, model: Model | None = None) -> list[dict[str, Any]]:
        del model
        as_of = market.valuation_date if market is not None else date.min
        years = years_to_maturity(self, as_of) if as_of != date.min else max(self.duration, 0.0)
        rate = self.repo_rate or annual_rate(self)
        interest = self.market_value_base * rate * years
        return [
            {
                "type": "repo_interest",
                "rate": rate,
                "haircut": self.haircut,
                "amount": interest,
            },
            {
                "type": "repo_principal",
                "years": years,
                "amount": self.market_value_base,
            },
        ]

    def value(self, market: Market, model: Model | None = None) -> float:
        del model
        if market is None:
            return float(self.market_value_base)
        wrapped = market.curves.get("repo_carry") if market is not None else None
        if callable(wrapped):
            as_of = market.valuation_date
            years = years_to_maturity(self, as_of) if as_of is not None else max(self.duration, 0.0)
            return float(
                wrapped(
                    self.repo_rate or annual_rate(self),
                    years,
                    self.market_value_base,
                    0.0,
                    self.haircut,
                )
            )
        return _reprice(self, market, 0.0)

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        base = self.value(market)
        rate_shift = _rate_shift(self, market, shocks)
        wrapped = market.curves.get("repo_carry") if market is not None else None
        if callable(wrapped):
            as_of = market.valuation_date
            years = years_to_maturity(self, as_of) if as_of is not None else max(self.duration, 0.0)
            shocked = float(
                wrapped(
                    self.repo_rate or annual_rate(self),
                    years,
                    self.market_value_base,
                    rate_shift,
                    self.haircut,
                )
            )
        else:
            shocked = _reprice(self, market, rate_shift) if market is not None else base
        shocked *= _fx_multiplier(self, market, shocks)
        return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}
