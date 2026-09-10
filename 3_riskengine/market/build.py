"""Build FinancePy-style Market from an ARISK portfolio snapshot.

Curve callables are bound to the FinancePy adapter when the engine is provided.
Products never import financepy / ORE / riskfolio.
"""
from __future__ import annotations

from typing import Any

from ..core.contracts import Market


def market_from_snapshot(snapshot: Any, engine: Any | None = None) -> Market:
    prices: dict[str, float] = {}
    fx: dict[str, float] = {}
    for position in getattr(snapshot, "positions", ()):
        code = str(position.security_code)
        prices[code] = float(position.market_value)
        fx[str(position.currency)] = float(getattr(position, "fx_rate", 1.0) or 1.0)
    fx.setdefault(str(snapshot.reporting_currency), 1.0)
    market = Market(
        valuation_date=snapshot.as_of_date,
        prices=prices,
        fx=fx,
        macro={
            "nav": float(snapshot.net_asset),
            "fund_id": getattr(snapshot, "fund_id", ""),
            "reporting_currency": str(snapshot.reporting_currency),
        },
    )
    adapter = getattr(engine, "financepy", None) if engine is not None else None
    ore = getattr(engine, "ore", None) if engine is not None else None
    as_of = snapshot.as_of_date
    if adapter is not None and getattr(adapter, "available", False):
        market.curves["engine"] = "FinancePy"
        market.curves["discount_factor"] = lambda rate, years: adapter.discount_factor(rate, years, as_of)
        market.curves["shocked_discount_factor"] = (
            lambda rate, shock, years: adapter.shocked_discount_factor(rate, shock, years, as_of)
        )
        market.curves["reprice_from_ytm"] = (
            lambda rate, years, mv, shock: adapter.reprice_from_ytm(rate, years, mv, shock, as_of)
        )
    else:
        market.curves["engine"] = "riskengine_exp"
    if ore is not None and getattr(ore, "available", False):
        market.curves["ore_engine"] = "ORE" if getattr(ore, "ore_swig_available", False) else "QuantLib"
        market.curves["ore_reprice"] = lambda product, shocks=(): ore.price_product(product, as_of, tuple(shocks))
    return market
