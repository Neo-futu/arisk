"""Aggregate product-level valuation rows into portfolio / fund books."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from ..core.contracts import ViewMode


def _nav(snapshot: Any) -> float:
    return float(getattr(snapshot, "net_asset", 0.0) or 0.0)


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"base_pv": 0.0, "shocked_pv": 0.0, "pnl": 0.0})
    for row in rows:
        bucket = buckets[str(row.get(key) or "OTHER")]
        bucket["base_pv"] += float(row["base_pv"])
        bucket["shocked_pv"] += float(row["shocked_pv"])
        bucket["pnl"] += float(row["pnl"])
    nav = sum(abs(item["base_pv"]) for item in buckets.values()) or 1.0
    out: dict[str, dict[str, Any]] = {}
    for name, bucket in buckets.items():
        pv = float(bucket["base_pv"])
        out[name] = {
            "base_pv": pv,
            "shocked_pv": float(bucket["shocked_pv"]),
            "pnl": float(bucket["pnl"]),
            "weight": pv / nav if nav else 0.0,
        }
    return dict(sorted(out.items(), key=lambda item: abs(item[1]["base_pv"]), reverse=True))


def aggregate(
    bound: Any,
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
    shocks: Iterable[Any] = (),
) -> dict[str, Any]:
    """Sum product valuation into one book. No vendor imports."""

    priced = bound.valuation().revalue(tuple(shocks), view=view)
    snapshot = bound.snapshot
    nav = _nav(snapshot)
    rows: list[dict[str, Any]] = []
    for item in priced.trade_values:
        pv = float(item["base_pv"])
        rows.append(
            {
                **item,
                "weight": (pv / nav) if nav else 0.0,
            }
        )
    gross = sum(abs(float(item["base_pv"])) for item in rows)
    net = sum(float(item["base_pv"]) for item in rows)
    return {
        "fund_id": str(getattr(snapshot, "fund_id", "") or ""),
        "as_of": snapshot.as_of_date.isoformat(),
        "reporting_currency": str(snapshot.reporting_currency),
        "view": str(getattr(view, "value", view)),
        "nav": nav,
        "base_pv": float(priced.base_pv),
        "shocked_pv": float(priced.shocked_pv),
        "pnl": float(priced.pnl),
        "gross": gross,
        "net": net,
        "leverage": (gross / nav) if nav else None,
        "positions": rows,
        "by_asset_class": _group(rows, "asset_class"),
        "by_engine": _group(rows, "engine"),
        "position_count": len(rows),
    }
