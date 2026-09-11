"""Trading use cases: proposed trades, pre/post-trade risk, order lifecycle."""
from __future__ import annotations

from typing import Any, Mapping

from importlib import import_module

from .proposed import apply_proposed_trade

_pre = import_module("4_business.risk_governance.pre_trade")
_life = import_module("4_business.trading.lifecycle")


def pre_trade(snapshot: Any, order: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return _pre.run_pre_trade(snapshot, order, **kwargs)


def submit_order(snapshot: Any, order: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return _life.submit_order(snapshot, order, **kwargs)


def execution(snapshot: Any, order: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    result = _life.submit_order(snapshot, order, **kwargs)
    return result.get("execution") or result


def position(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    return _life.current_position(snapshot, **kwargs)


def post_trade(snapshot: Any, order: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return _life.post_trade(snapshot, order, **kwargs)
