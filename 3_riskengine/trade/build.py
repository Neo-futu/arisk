"""Trade DTOs from platform holdings. Vendor mapping stays in adapters/ore/trade.py."""
from __future__ import annotations

from typing import Any

from ..core.contracts import Trade, ViewMode
from ..products.assemble import products_from_snapshot


def trade_from_product(product: Any) -> Trade:
    meta = dict(getattr(product, "metadata", None) or {})
    instrument = product.instrument
    return Trade(
        trade_id=str(instrument.instrument_id),
        instrument=instrument,
        counterparty=str(meta.get("counterparty") or meta.get("issuer") or ""),
        quantity=float(getattr(product, "notional", 0.0) or getattr(product, "quantity", 0.0) or 0.0),
        netting_set=meta.get("netting_set"),
        collateral_agreement=meta.get("csa") or meta.get("collateral_agreement"),
        metadata=meta,
    )


def trades_from_snapshot(snapshot: Any, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> list[Trade]:
    return [trade_from_product(item) for item in products_from_snapshot(snapshot, view=view)]
