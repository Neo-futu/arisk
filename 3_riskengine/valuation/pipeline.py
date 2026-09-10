"""Product + Market + Model valuation. Vendors stay behind adapters / Market callables."""
from __future__ import annotations

from typing import Any, Iterable

from ..core.contracts import AnalyticKind, ViewMode
from ..instruments.shocks import applicable_shocks, flip_shock
from ..models.catalog import model_for_ref
from ..products.assemble import products_from_snapshot


def _nav(snapshot: Any) -> float:
    return float(getattr(snapshot, "net_asset", 0.0) or 0.0)


def _rows(
    bound: Any,
    shocks: tuple[Any, ...] = (),
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
    analytic: AnalyticKind | str = AnalyticKind.PRICE,
) -> list[dict[str, Any]]:
    market = bound.market()
    products = products_from_snapshot(bound.snapshot, view=view)
    engine = bound.engine
    rows: list[dict[str, Any]] = []
    for product in products:
        ref = engine.resolve(product, analytic)
        model = model_for_ref(ref)
        filtered = applicable_shocks(product, shocks, market)
        if filtered:
            pack = product.sensitivity(market, filtered)
            base = float(pack.get("base_pv", 0.0))
            shocked = float(pack.get("shocked_pv", base))
        else:
            base = float(product.value(market, model))
            shocked = base
        rows.append(
            {
                "security_code": product.instrument.instrument_id,
                "security_name": product.instrument.name,
                "asset_class": product.kind.value,
                "base_pv": base,
                "shocked_pv": shocked,
                "pnl": shocked - base,
                "engine": ref.adapter,
                "model": ref.model,
            }
        )
    return sorted(rows, key=lambda item: abs(item["pnl"]), reverse=True)


def revalue(
    bound: Any,
    shocks: Iterable[Any] = (),
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> dict[str, Any]:
    shock_tuple = tuple(shocks)
    trade_values = _rows(bound, shock_tuple, view=view, analytic=AnalyticKind.PRICE)
    base_pv = sum(item["base_pv"] for item in trade_values)
    shocked_pv = sum(item["shocked_pv"] for item in trade_values)
    nav = _nav(bound.snapshot)
    return {
        "base_pv": base_pv,
        "shocked_pv": shocked_pv,
        "pnl": shocked_pv - base_pv,
        "pnl_pct_nav": ((shocked_pv - base_pv) / nav * 100.0) if nav else None,
        "trade_values": trade_values,
        "view": str(getattr(view, "value", view)),
    }


def greeks(
    bound: Any,
    shocks: Iterable[Any],
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for shock in shocks:
        up = revalue(bound, (shock,), view=view)
        down = revalue(bound, (flip_shock(shock),), view=view)
        denominator = shock.value if shock.value else 1.0
        factor = str(getattr(shock.factor_type, "value", shock.factor_type))
        rows.append(
            {
                "factor_type": factor,
                "label": shock.label or factor,
                "tenor": shock.tenor,
                "currency": shock.currency,
                "shock": shock.value,
                "mode": str(getattr(shock.mode, "value", shock.mode)),
                "up_pnl": up["pnl"],
                "down_pnl": down["pnl"],
                "delta": (up["pnl"] - down["pnl"]) / (2.0 * denominator),
                "gamma": (up["pnl"] + down["pnl"]) / (denominator * denominator),
                "pnl_pct_nav": up["pnl_pct_nav"],
            }
        )
    return {"analytic": "SENSITIVITY", "sensitivities": rows, "view": str(getattr(view, "value", view))}


def cashflows(
    bound: Any,
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> dict[str, Any]:
    market = bound.market()
    products = products_from_snapshot(bound.snapshot, view=view)
    engine = bound.engine
    items: list[dict[str, Any]] = []
    for product in products:
        ref = engine.resolve(product, AnalyticKind.CASHFLOW)
        model = model_for_ref(ref)
        items.append(
            {
                "security_code": product.instrument.instrument_id,
                "security_name": product.instrument.name,
                "asset_class": product.kind.value,
                "engine": ref.adapter,
                "model": ref.model,
                "flows": product.cashflows(market, model),
            }
        )
    return {
        "analytic": "CASHFLOW",
        "view": str(getattr(view, "value", view)),
        "products": items,
    }
