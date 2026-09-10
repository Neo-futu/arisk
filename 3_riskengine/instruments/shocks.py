"""Shock filters shared by products and unified valuation. No vendor imports."""
from __future__ import annotations

from typing import Any, Iterable

from .classify import krd_bucket


def reporting_currency(market: Any, product: Any) -> str:
    if market is None:
        return str(getattr(product, "currency", "") or "")
    macro = getattr(market, "macro", None) or {}
    return str(macro.get("reporting_currency") or getattr(product, "currency", "") or "")


def applicable_shocks(product: Any, shocks: Iterable[Any], market: Any) -> tuple[Any, ...]:
    as_of = getattr(market, "valuation_date", None) if market is not None else None
    bucket = krd_bucket(product, as_of) if as_of is not None else None
    kept: list[Any] = []
    for shock in shocks:
        currency = getattr(shock, "currency", None)
        if currency and currency != getattr(product, "currency", None):
            continue
        tenor = getattr(shock, "tenor", None)
        if tenor and bucket is not None and tenor != bucket:
            continue
        kept.append(shock)
    return tuple(kept)


def flip_shock(shock: Any) -> Any:
    return type(shock)(
        shock.factor_type,
        -shock.value,
        shock.mode,
        shock.tenor,
        shock.currency,
        shock.label,
    )


def shock_as_dict(shock: Any) -> dict[str, Any]:
    factor = getattr(shock, "factor_type", None)
    mode = getattr(shock, "mode", None)
    return {
        "factor_type": str(getattr(factor, "value", factor)),
        "value": shock.value,
        "mode": str(getattr(mode, "value", mode)),
        "tenor": shock.tenor,
        "currency": shock.currency,
        "label": shock.label,
    }


def scale_shocks(shocks: Iterable[Any], scale: float) -> tuple[Any, ...]:
    return tuple(
        type(shock)(
            shock.factor_type,
            shock.value * scale,
            shock.mode,
            shock.tenor,
            shock.currency,
            shock.label,
        )
        for shock in shocks
    )
