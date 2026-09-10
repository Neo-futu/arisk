"""Equity spot product. Price comes from Market; no vendor import."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.contracts import Market, Product, ProductKind, Shock
from ..instruments.shocks import applicable_shocks, reporting_currency


@dataclass
class Equity(Product):
    def __post_init__(self) -> None:
        self.kind = ProductKind.EQUITY
        super().__post_init__()

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        base = self.value(market)
        equity_rel = 0.0
        fx_rel = 0.0
        vol_rel = 0.0
        for shock in applicable_shocks(self, shocks, market):
            key = str(getattr(shock.factor_type, "value", shock.factor_type))
            mode = str(getattr(shock.mode, "value", shock.mode))
            increment = shock.value if mode == "RELATIVE" else shock.value
            if key == "EQUITY":
                equity_rel += increment
            elif key == "FX":
                fx_rel += increment
            elif key == "VOLATILITY":
                vol_rel += increment
        shocked = base * (1.0 + equity_rel)
        observed_volatility = float((self.metadata or {}).get("historical_volatility", 0.20))
        shocked += self.market_value_base * observed_volatility * 0.40 * vol_rel
        reporting = reporting_currency(market, self)
        if self.currency != reporting:
            shocked *= 1.0 + fx_rel
        return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}
