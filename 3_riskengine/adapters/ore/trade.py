"""ORE trade descriptors. No OREApp XML — business code never builds vendor trades."""
from __future__ import annotations

from typing import Any

from ...core.contracts import ProductKind, Trade

_TRADE_TYPE = {
    ProductKind.FX.value: "FxSpot",
    ProductKind.FX_FORWARD.value: "FxForward",
    ProductKind.FX_OPTION.value: "FxOption",
    ProductKind.FUTURE.value: "Future",
    ProductKind.OPTION.value: "EquityOption",
    ProductKind.IRS.value: "Swap",
    ProductKind.SWAP.value: "Swap",
    ProductKind.SWAPTION.value: "Swaption",
    ProductKind.CDS.value: "CreditDefaultSwap",
    ProductKind.BOND.value: "Bond",
    ProductKind.EQUITY.value: "Equity",
    ProductKind.CASH.value: "Cash",
    ProductKind.DEPOSIT.value: "Cash",
    ProductKind.CD.value: "Bond",
    ProductKind.MMF.value: "Fund",
}


def descriptor_from_product(product: Any) -> dict[str, Any]:
    kind = str(getattr(getattr(product, "kind", None), "value", getattr(product, "kind", "CASH")))
    instrument = getattr(product, "instrument", None)
    meta = dict(getattr(product, "metadata", None) or {})
    maturity = getattr(product, "maturity_date", None) or getattr(instrument, "maturity_date", None)
    return {
        "id": getattr(instrument, "instrument_id", "") if instrument is not None else meta.get("id", ""),
        "type": _TRADE_TYPE.get(kind, kind),
        "product_kind": kind,
        "currency": getattr(product, "currency", ""),
        "notional": float(getattr(product, "notional", 0.0) or getattr(product, "market_value_base", 0.0) or 0.0),
        "counterparty": str(meta.get("counterparty") or meta.get("issuer") or ""),
        "maturity": maturity.isoformat() if maturity is not None else None,
        "strike": float(getattr(product, "strike", 0.0) or meta.get("strike") or 0.0),
        "option_type": str(getattr(product, "option_type", "") or meta.get("option_type") or ""),
        "exercise": str(getattr(product, "exercise", "") or meta.get("exercise") or ""),
        "pair": str(getattr(product, "pair", "") or meta.get("pair") or ""),
        "netting_set": meta.get("netting_set"),
        "collateral_agreement": meta.get("csa") or meta.get("collateral_agreement"),
        "ore_app": False,
    }


def trade_from_product(product: Any) -> Trade:
    descriptor = descriptor_from_product(product)
    instrument = product.instrument
    return Trade(
        trade_id=str(descriptor["id"] or instrument.instrument_id),
        instrument=instrument,
        counterparty=str(descriptor["counterparty"] or ""),
        quantity=float(getattr(product, "notional", 0.0) or getattr(product, "quantity", 0.0) or 0.0),
        netting_set=descriptor.get("netting_set"),
        collateral_agreement=descriptor.get("collateral_agreement"),
        metadata={**dict(getattr(product, "metadata", None) or {}), "ore_trade": descriptor},
    )
