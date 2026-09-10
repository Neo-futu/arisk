"""Cash balance product."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.contracts import Market, Model, Product, ProductKind, Shock
from ..instruments.shocks import applicable_shocks, reporting_currency


@dataclass
class Cash(Product):
    def __post_init__(self) -> None:
        self.kind = ProductKind.CASH
        super().__post_init__()

    def cashflows(self, market: Market, model: Model | None = None) -> list[dict[str, Any]]:
        del model
        return [{"type": "balance", "amount": self.value(market)}]

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        base = self.value(market)
        reporting = reporting_currency(market, self)
        fx_rel = 0.0
        for shock in applicable_shocks(self, shocks, market):
            key = str(getattr(shock.factor_type, "value", shock.factor_type))
            if key == "FX":
                fx_rel += float(shock.value)
        shocked = base * (1.0 + fx_rel) if self.currency != reporting else base
        return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}
