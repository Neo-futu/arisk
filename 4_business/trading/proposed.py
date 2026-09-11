"""Apply a proposed order onto a cloned snapshot. Does not write fsi.balance_*."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from importlib import import_module

models = import_module("2_processing.tools.risk_testing.models")
Position = models.Position


def apply_proposed_trade(snapshot: Any, order: Mapping[str, Any]) -> Any:
    proposed = deepcopy(snapshot)
    side = str(order.get("side") or "BUY").upper()
    sign = 1.0 if side == "BUY" else -1.0
    amount = abs(float(order["amount"])) * sign
    code = str(order["security_code"])
    currency = str(order.get("currency") or snapshot.reporting_currency)
    fx = float(order.get("fx_rate") or 1.0) or 1.0
    metadata = {
        "issuer": order.get("issuer") or order.get("issuer_name"),
        "issuer_name": order.get("issuer") or order.get("issuer_name"),
        "sector": order.get("sector"),
        "country": order.get("country"),
        "counterparty": order.get("counterparty"),
    }
    metadata = {k: v for k, v in metadata.items() if v}

    updated = False
    new_positions = []
    cash_index = None
    for index, position in enumerate(proposed.positions):
        if position.security_code == code:
            merged = dict(position.metadata)
            merged.update(metadata)
            new_positions.append(
                Position(
                    security_code=position.security_code,
                    security_name=position.security_name,
                    asset_class=position.asset_class,
                    currency=position.currency,
                    market_value=position.market_value + amount / fx,
                    market_value_base=position.market_value_base + amount,
                    duration=float(order.get("duration") or position.duration),
                    convexity=position.convexity,
                    ytm=position.ytm,
                    coupon_rate=position.coupon_rate,
                    maturity_date=position.maturity_date,
                    fx_rate=position.fx_rate,
                    metadata=merged,
                )
            )
            updated = True
        else:
            new_positions.append(position)
        if position.asset_class == "CASH" and cash_index is None:
            cash_index = len(new_positions) - 1

    if not updated:
        new_positions.append(
            Position(
                security_code=code,
                security_name=str(order.get("security_name") or code),
                asset_class=str(order.get("asset_class") or "EQUITY"),
                currency=currency,
                market_value=amount / fx,
                market_value_base=amount,
                duration=float(order.get("duration") or 0.0),
                fx_rate=fx,
                metadata=metadata,
            )
        )

    if cash_index is not None and new_positions[cash_index].security_code != code:
        cash = new_positions[cash_index]
        new_positions[cash_index] = Position(
            security_code=cash.security_code,
            security_name=cash.security_name,
            asset_class=cash.asset_class,
            currency=cash.currency,
            market_value=cash.market_value - amount,
            market_value_base=cash.market_value_base - amount,
            duration=cash.duration,
            convexity=cash.convexity,
            ytm=cash.ytm,
            coupon_rate=cash.coupon_rate,
            maturity_date=cash.maturity_date,
            fx_rate=cash.fx_rate,
            metadata=dict(cash.metadata),
        )

    proposed.positions = new_positions
    quality = dict(proposed.data_quality or {})
    quality["source"] = "proposed_trade"
    quality["is_live"] = False
    proposed.data_quality = quality
    return proposed
