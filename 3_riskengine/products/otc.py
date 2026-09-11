"""OTC / listed derivative product base. Pricing callables live on Market (ORE adapter)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..core.contracts import Market, Model, Product, Shock


def _ore_pack(product: Product, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any] | None:
    if market is None:
        return None
    fn = (market.curves or {}).get("ore_reprice")
    if not callable(fn):
        return None
    pack = fn(product, shocks)
    return pack if isinstance(pack, dict) else None


@dataclass
class OtcProduct(Product):
    """Shared terms for FX / listed / rates / credit products."""

    notional: float = 0.0
    strike: float = 0.0
    volatility: float = 0.20
    option_type: str = "Call"
    exercise: str = "European"
    underlying: str = ""
    pair: str = ""
    spot: float = 0.0
    domestic_rate: float = 0.03
    foreign_rate: float = 0.03
    hazard_rate: float = 0.01
    recovery_rate: float = 0.40
    pay_fixed: bool = True
    protection_seller: bool = False
    tenor_years: float = 5.0
    option_tenor_years: float = 1.0
    maturity_date: date | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.notional:
            self.notional = float(self.market_value_base or self.market_value or 0.0)
        if not self.spot:
            self.spot = float((self.metadata or {}).get("spot") or self.fx_rate or 0.0)

    def value(self, market: Market, model: Model | None = None) -> float:
        del model
        pack = _ore_pack(self, market, ())
        if pack is not None:
            return float(pack.get("base_pv", self.market_value_base))
        return float(self.market_value_base)

    def cashflows(self, market: Market, model: Model | None = None) -> list[dict[str, Any]]:
        del model
        pack = _ore_pack(self, market, ())
        if pack and pack.get("cashflows"):
            return list(pack["cashflows"])
        return [
            {
                "type": "otc",
                "kind": self.kind.value,
                "notional": self.notional,
                "amount": self.value(market),
            }
        ]

    def sensitivity(self, market: Market, shocks: tuple[Shock, ...] = ()) -> dict[str, Any]:
        pack = _ore_pack(self, market, shocks)
        if pack is not None:
            base = float(pack.get("base_pv", self.market_value_base))
            shocked = float(pack.get("shocked_pv", base))
            return {
                "base_pv": base,
                "shocked_pv": shocked,
                "pnl": shocked - base,
                "library": pack.get("library"),
                "trade_type": pack.get("trade_type"),
            }
        base = self.value(market)
        return {"base_pv": base, "shocked_pv": base, "pnl": 0.0}
