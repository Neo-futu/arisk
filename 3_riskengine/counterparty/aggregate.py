"""Product/trade exposure, then counterparty / netting / allocated XVA."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from ..core.contracts import ViewMode
from ..instruments.classify import issuer_name
from ..products.assemble import product_from_holding


def _counterparty_of(product: Any) -> str:
    meta = dict(getattr(product, "metadata", None) or {})
    name = str(meta.get("counterparty") or meta.get("issuer") or "")
    if name:
        return name
    return issuer_name(product)


def _netting_of(product: Any) -> str:
    meta = dict(getattr(product, "metadata", None) or {})
    return str(meta.get("netting_set") or _counterparty_of(product) or "UNASSIGNED")


def exposure_rows(bound: Any) -> list[dict[str, Any]]:
    priced = bound.valuation().price(view=ViewMode.LOOK_THROUGH)
    pv_by_code = {item["security_code"]: float(item["base_pv"]) for item in priced.trade_values}
    mapping = bound.engine.ore.map_snapshot(bound.snapshot)
    descriptor = {item["id"]: item for item in mapping.get("trades", [])}
    rows: list[dict[str, Any]] = []
    for position in bound.snapshot.positions:
        product = product_from_holding(position)
        code = position.security_code
        trade = descriptor.get(code, {})
        pv = float(pv_by_code.get(code, position.market_value_base))
        rows.append(
            {
                "security_code": code,
                "asset_class": str(getattr(product.kind, "value", product.kind)),
                "counterparty": str(trade.get("counterparty") or _counterparty_of(product)),
                "netting_set": str(trade.get("netting_set") or _netting_of(product) or "UNASSIGNED"),
                "trade_type": str(trade.get("type") or product.kind),
                "base_pv": pv,
                "notional": float(trade.get("notional") or pv),
            }
        )
    return sorted(rows, key=lambda item: abs(item["base_pv"]), reverse=True)


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"base_pv": 0.0, "notional": 0.0, "count": 0})
    for row in rows:
        name = str(row.get(key) or "UNASSIGNED")
        bucket = buckets[name]
        bucket["base_pv"] += float(row["base_pv"])
        bucket["notional"] += float(row["notional"])
        bucket["count"] += 1
    nav = float(sum(abs(item["base_pv"]) for item in buckets.values()) or 1.0)
    out: dict[str, dict[str, Any]] = {}
    for name, bucket in buckets.items():
        pv = float(bucket["base_pv"])
        out[name] = {**bucket, "weight": abs(pv) / nav if nav else 0.0}
    return dict(sorted(out.items(), key=lambda item: abs(item[1]["base_pv"]), reverse=True))


def allocate_xva(rows: list[dict[str, Any]], xva: Mapping[str, Any]) -> list[dict[str, Any]]:
    mass = sum(abs(float(item["base_pv"])) for item in rows) or 1.0
    cva = float(xva.get("cva") or 0.0)
    dva = float(xva.get("dva") or 0.0)
    fva = float(xva.get("fva") or 0.0)
    mva = float(xva.get("mva") or 0.0)
    allocated = []
    for row in rows:
        weight = abs(float(row["base_pv"])) / mass
        allocated.append(
            {
                **row,
                "weight": weight,
                "cva": cva * weight,
                "dva": dva * weight,
                "fva": fva * weight,
                "mva": mva * weight,
                "total_xva": (cva - dva + fva + mva) * weight,
            }
        )
    return allocated


def report(bound: Any, xva: Mapping[str, Any]) -> dict[str, Any]:
    rows = allocate_xva(exposure_rows(bound), xva)
    by_cp = _group(rows, "counterparty")
    for name, bucket in by_cp.items():
        members = [item for item in rows if item["counterparty"] == name]
        bucket["cva"] = sum(item["cva"] for item in members)
        bucket["total_xva"] = sum(item["total_xva"] for item in members)
    return {
        "positions": rows,
        "by_counterparty": by_cp,
        "by_netting_set": _group(rows, "netting_set"),
        "by_asset_class": _group(rows, "asset_class"),
        "cva": float(xva.get("cva") or 0.0),
        "dva": float(xva.get("dva") or 0.0),
        "fva": float(xva.get("fva") or 0.0),
        "mva": float(xva.get("mva") or 0.0),
        "total_xva": float(xva.get("total_xva") or 0.0),
        "ore_app": False,
        "library": xva.get("library"),
        "exposure_profile": xva.get("exposure_profile") or [],
    }
