"""Build FinancePy-style Market from an ARISK portfolio snapshot.

``Market.prices`` are **unit market quotes** (close / dirty / NAV), never position
``market_value``. Prefer ``snapshot.market_panel`` loaded from ``fsi.mktdata_*``
(+ optional OpenBB gaps). Curve callables bind to FinancePy / ORE adapters.
"""
from __future__ import annotations

from typing import Any

from ..core.contracts import Market
from .asof import AsOfMarketPanel, attach_market_panel, panel_from_positions


def _panel_of(snapshot: Any) -> AsOfMarketPanel:
    panel = getattr(snapshot, "market_panel", None)
    if isinstance(panel, AsOfMarketPanel):
        return panel
    derived = panel_from_positions(snapshot)
    attach_market_panel(snapshot, derived)
    return derived


def market_from_snapshot(snapshot: Any, engine: Any | None = None) -> Market:
    panel = _panel_of(snapshot)
    quality = panel.quality()
    vols: dict[str, float] = {}
    for position in getattr(snapshot, "positions", ()) or ():
        meta = getattr(position, "metadata", None) or {}
        vol = meta.get("historical_volatility")
        if vol is not None:
            vols[str(position.security_code)] = float(vol)

    market = Market(
        valuation_date=snapshot.as_of_date,
        prices=dict(panel.prices),
        fx=dict(panel.fx),
        volatility=vols,
        macro={
            "nav": float(snapshot.net_asset),
            "fund_id": getattr(snapshot, "fund_id", ""),
            "reporting_currency": str(snapshot.reporting_currency),
            "market_data_kind": "quotes",
            "bond_risk": dict(panel.bond_risk),
            "quote_dates": {k: v.isoformat() for k, v in panel.quote_dates.items()},
            "sources": dict(panel.sources),
            "fields": dict(panel.fields),
            "data_quality": quality,
            "warnings": list(panel.warnings),
            "missing": list(panel.missing),
            "stale": list(panel.stale),
            "abnormal": list(panel.abnormal),
            "benchmark_id": getattr(snapshot, "benchmark_id", None) or panel.benchmark_id,
            "index_levels": dict(panel.index_levels),
            "benchmark_return_count": len(
                getattr(snapshot, "benchmark_returns", None) or panel.benchmark_returns or ()
            ),
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
        market.curves["repo_carry"] = (
            lambda rate, years, mv, shock, haircut=0.0: adapter.repo_carry(
                rate, years, mv, shock, haircut, as_of
            )
        )
    else:
        market.curves["engine"] = "riskengine_exp"
        market.curves["repo_carry"] = (
            lambda rate, years, mv, shock, haircut=0.0: float(mv)
            if abs(float(shock)) < 1e-15
            else float(mv) * (1.0 - float(years) * float(shock))
        )
    if ore is not None and getattr(ore, "available", False):
        market.curves["ore_engine"] = "ORE" if getattr(ore, "ore_swig_available", False) else "QuantLib"
        market.curves["ore_reprice"] = lambda product, shocks=(): ore.price_product(product, as_of, tuple(shocks))
    return market
