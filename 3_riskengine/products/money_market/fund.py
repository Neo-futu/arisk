"""MMF as a first-class product: share-class NAV view and look-through holdings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ...core.contracts import Market, Model, Product, ProductKind, Shock, ViewMode
from ...instruments.classify import days_to_maturity
from ...instruments.shocks import applicable_shocks, reporting_currency


@dataclass
class MoneyMarketFund(Product):
    """Money-market fund. Holdings are Bond / Deposit / CD / Cash / nested funds."""

    holdings: list[Product] = field(default_factory=list)
    nav: float = 0.0
    view: ViewMode = ViewMode.PRODUCT

    def __post_init__(self) -> None:
        self.kind = ProductKind.MMF
        super().__post_init__()
        if not self.nav:
            self.nav = float(self.market_value_base)

    def look_through(self) -> list[Product]:
        return list(self.holdings)

    def _use_look_through(self, model: Model | None) -> bool:
        if model is not None:
            view = str((model.parameters or {}).get("view") or "")
            if view == ViewMode.LOOK_THROUGH.value:
                return True
            if view == ViewMode.PRODUCT.value:
                return False
        return self.view is ViewMode.LOOK_THROUGH and bool(self.holdings)

    def value(self, market: Market, model: Model | None = None) -> float:
        if self._use_look_through(model) and self.holdings:
            return float(sum(item.value(market, model) for item in self.holdings))
        return super().value(market, model)

    def cashflows(self, market: Market, model: Model | None = None) -> list[dict[str, Any]]:
        if self._use_look_through(model):
            flows: list[dict[str, Any]] = []
            for item in self.holdings:
                flows.extend(item.cashflows(market, model))
            return flows
        return [{"type": "nav", "amount": self.value(market, model)}]

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        if self.holdings:
            packs = [item.sensitivity(market, shocks) for item in self.holdings]
            base = sum(float(pack.get("base_pv", 0.0)) for pack in packs)
            shocked = sum(float(pack.get("shocked_pv", 0.0)) for pack in packs)
            return {
                "base_pv": base,
                "shocked_pv": shocked,
                "pnl": shocked - base,
                "view": ViewMode.LOOK_THROUGH.value,
            }
        base = self.value(market)
        reporting = reporting_currency(market, self)
        fx_rel = 0.0
        for shock in applicable_shocks(self, shocks, market):
            key = str(getattr(shock.factor_type, "value", shock.factor_type))
            if key == "FX":
                fx_rel += float(shock.value)
        shocked = base * (1.0 + fx_rel) if self.currency != reporting else base
        return {
            "base_pv": base,
            "shocked_pv": shocked,
            "pnl": shocked - base,
            "view": ViewMode.PRODUCT.value,
        }

    def wam_days(self, as_of) -> float:
        return self._weighted_days(as_of, wal=False)

    def wal_days(self, as_of) -> float:
        return self._weighted_days(as_of, wal=True)

    def _weighted_days(self, as_of, *, wal: bool) -> float:
        rows = self.holdings or []
        weighted = 0.0
        mass = 0.0
        for item in rows:
            mv = float(item.market_value_base)
            if mv <= 0:
                continue
            if item.kind is ProductKind.CASH:
                days = 0.0
            elif wal:
                days = days_to_maturity(item, as_of)
            else:
                reset = (item.metadata or {}).get("reset_days")
                days = float(reset) if reset is not None else days_to_maturity(item, as_of)
            weighted += mv * days
            mass += mv
        return weighted / mass if mass else 0.0


def is_money_market_book(products: Iterable[Product]) -> bool:
    allowed = {
        ProductKind.BOND,
        ProductKind.CD,
        ProductKind.DEPOSIT,
        ProductKind.CASH,
        ProductKind.MMF,
        ProductKind.FUND,
        ProductKind.ETF,
    }
    kinds = {item.kind for item in products}
    return bool(kinds) and kinds <= allowed
