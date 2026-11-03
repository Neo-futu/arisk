"""克隆持仓并叠加拟成交指令（不写库）。

独立于 ``4_business.trading.proposed``：不 import ``2_processing``；
按现有持仓推断 Position 类型（duck-type），兼容测试夹具与线上 snapshot。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def apply_proposed_trade(snapshot: Any, order: Mapping[str, Any]) -> Any:
    """在 snapshot 深拷贝上叠加 BUY/SELL，返回试算持仓（is_live=False）。"""

    proposed = deepcopy(snapshot)
    side = str(order.get("side") or "BUY").upper()
    sign = 1.0 if side == "BUY" else -1.0
    amount = abs(float(order["amount"])) * sign
    code = str(order["security_code"])
    currency = str(order.get("currency") or getattr(snapshot, "reporting_currency", "HKD"))
    fx = float(order.get("fx_rate") or 1.0) or 1.0
    metadata = {
        "issuer": order.get("issuer") or order.get("issuer_name"),
        "issuer_name": order.get("issuer") or order.get("issuer_name"),
        "sector": order.get("sector"),
        "country": order.get("country"),
        "counterparty": order.get("counterparty"),
    }
    metadata = {k: v for k, v in metadata.items() if v}

    positions = list(getattr(proposed, "positions", ()) or ())
    if not positions:
        raise ValueError("snapshot has no positions to apply proposed trade")
    pos_cls = type(positions[0])

    updated = False
    new_positions: list[Any] = []
    cash_index = None

    for position in positions:
        if str(getattr(position, "security_code", "")) == code:
            merged = dict(getattr(position, "metadata", None) or {})
            merged.update(metadata)
            new_positions.append(
                _rebuild(
                    pos_cls,
                    position,
                    market_value=float(position.market_value) + amount / fx,
                    market_value_base=float(position.market_value_base) + amount,
                    duration=float(order.get("duration") or getattr(position, "duration", 0.0) or 0.0),
                    metadata=merged,
                )
            )
            updated = True
        else:
            new_positions.append(position)
        if str(getattr(position, "asset_class", "")) == "CASH" and cash_index is None:
            cash_index = len(new_positions) - 1

    if not updated:
        template = positions[0]
        new_positions.append(
            _rebuild(
                pos_cls,
                template,
                security_code=code,
                security_name=str(order.get("security_name") or code),
                asset_class=str(order.get("asset_class") or "EQUITY"),
                currency=currency,
                market_value=amount / fx,
                market_value_base=amount,
                duration=float(order.get("duration") or 0.0),
                convexity=0.0,
                ytm=0.0,
                coupon_rate=0.0,
                maturity_date=None,
                fx_rate=fx,
                metadata=metadata,
            )
        )

    if cash_index is not None and str(getattr(new_positions[cash_index], "security_code", "")) != code:
        cash = new_positions[cash_index]
        new_positions[cash_index] = _rebuild(
            pos_cls,
            cash,
            market_value=float(cash.market_value) - amount,
            market_value_base=float(cash.market_value_base) - amount,
            metadata=dict(getattr(cash, "metadata", None) or {}),
        )

    proposed.positions = new_positions
    quality = dict(getattr(proposed, "data_quality", None) or {})
    quality["source"] = "proposed_trade"
    quality["is_live"] = False
    proposed.data_quality = quality
    return proposed


def _rebuild(pos_cls: type, template: Any, **overrides: Any) -> Any:
    fields = {
        "security_code": getattr(template, "security_code", ""),
        "security_name": getattr(template, "security_name", ""),
        "asset_class": getattr(template, "asset_class", "OTHER"),
        "currency": getattr(template, "currency", "HKD"),
        "market_value": float(getattr(template, "market_value", 0.0) or 0.0),
        "market_value_base": float(getattr(template, "market_value_base", 0.0) or 0.0),
        "duration": float(getattr(template, "duration", 0.0) or 0.0),
        "convexity": float(getattr(template, "convexity", 0.0) or 0.0),
        "ytm": float(getattr(template, "ytm", 0.0) or 0.0),
        "coupon_rate": float(getattr(template, "coupon_rate", 0.0) or 0.0),
        "maturity_date": getattr(template, "maturity_date", None),
        "fx_rate": float(getattr(template, "fx_rate", 1.0) or 1.0),
        "metadata": dict(getattr(template, "metadata", None) or {}),
    }
    fields.update(overrides)
    try:
        return pos_cls(**fields)
    except TypeError:
        allowed = getattr(pos_cls, "__dataclass_fields__", None)
        if allowed:
            return pos_cls(**{k: v for k, v in fields.items() if k in allowed})
        raise
