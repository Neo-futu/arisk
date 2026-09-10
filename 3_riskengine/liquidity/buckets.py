"""Classify each product into a liquidity bucket, then aggregate."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..core.contracts import ProductKind, ViewMode
from ..instruments.classify import days_to_maturity
from ..products.assemble import products_from_snapshot

BUCKETS: tuple[str, ...] = ("T0", "1W", "1M", "3M", "6M", "ILLIQUID")
HAIRCUT: dict[str, float] = {
    "T0": 0.0,
    "1W": 0.01,
    "1M": 0.02,
    "3M": 0.05,
    "6M": 0.10,
    "ILLIQUID": 0.25,
}
LISTED = {ProductKind.EQUITY, ProductKind.ETF, ProductKind.FX, ProductKind.FUTURE}
OTC_STICKY = {
    ProductKind.IRS,
    ProductKind.SWAP,
    ProductKind.SWAPTION,
    ProductKind.CDS,
    ProductKind.STRUCTURED,
}


def bucket_for(product: Any, as_of) -> str:
    kind = product.kind if isinstance(product.kind, ProductKind) else ProductKind(str(product.kind))
    if kind is ProductKind.CASH or kind is ProductKind.MMF:
        return "T0"
    if kind in LISTED:
        return "1W"
    if kind in OTC_STICKY:
        return "ILLIQUID"
    days = float(days_to_maturity(product, as_of) or 0.0)
    if days <= 1:
        return "T0"
    if days <= 7:
        return "1W"
    if days <= 30:
        return "1M"
    if days <= 90:
        return "3M"
    if days <= 180:
        return "6M"
    return "ILLIQUID"


def _rows(bound: Any) -> list[dict[str, Any]]:
    as_of = bound.snapshot.as_of_date
    rows: list[dict[str, Any]] = []
    for product in products_from_snapshot(bound.snapshot, view=ViewMode.LOOK_THROUGH):
        pv = float(getattr(product, "market_value_base", 0.0) or 0.0)
        bucket = bucket_for(product, as_of)
        kind = str(getattr(product.kind, "value", product.kind))
        rows.append(
            {
                "security_code": product.instrument.instrument_id,
                "asset_class": kind,
                "bucket": bucket,
                "days": float(days_to_maturity(product, as_of) or 0.0),
                "base_pv": pv,
                "haircut": HAIRCUT[bucket],
                "advancable": pv * (1.0 - HAIRCUT[bucket]),
            }
        )
    return sorted(rows, key=lambda item: abs(item["base_pv"]), reverse=True)


def aggregate_buckets(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    buckets: dict[str, dict[str, float]] = {
        name: {"base_pv": 0.0, "advancable": 0.0, "count": 0.0} for name in BUCKETS
    }
    for row in rows:
        bucket = buckets[row["bucket"]]
        bucket["base_pv"] += float(row["base_pv"])
        bucket["advancable"] += float(row["advancable"])
        bucket["count"] += 1.0
    return buckets


def by_asset_class(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"base_pv": 0.0, "advancable": 0.0})
    for row in rows:
        bucket = grouped[str(row["asset_class"])]
        bucket["base_pv"] += float(row["base_pv"])
        bucket["advancable"] += float(row["advancable"])
    return dict(sorted(grouped.items(), key=lambda item: abs(item[1]["base_pv"]), reverse=True))


def report(bound: Any) -> dict[str, Any]:
    rows = _rows(bound)
    nav = float(bound.snapshot.net_asset or 0.0)
    buckets = aggregate_buckets(rows)
    liquid = buckets["T0"]["base_pv"] + buckets["1W"]["base_pv"] + buckets["1M"]["base_pv"]
    return {
        "positions": rows,
        "buckets": buckets,
        "by_asset_class": by_asset_class(rows),
        "liquid_pv": liquid,
        "liquid_pct_nav": (liquid / nav * 100.0) if nav else None,
        "advancable_pv": sum(item["advancable"] for item in buckets.values()),
    }
