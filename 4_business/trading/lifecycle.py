"""Trading lifecycle: Order → PreTrade → OMS/EMS/Broker → PostTrade.

External systems are reached only through 5_integrations adapters.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from .proposed import apply_proposed_trade

_pre = import_module("4_business.risk_governance.pre_trade")
_reg = import_module("5_integrations.registry")
_base = import_module("5_integrations.base")
_limits = import_module("3_riskengine.limits")

AdapterContext = _base.AdapterContext


def submit_order(
    snapshot: Any,
    order: Mapping[str, Any],
    *,
    context: AdapterContext | None = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = context or AdapterContext()
    pre = _pre.run_pre_trade(snapshot, order, policy=policy, actor=ctx.actor)
    if pre["decision"] == "REJECT":
        return {
            "status": "REJECTED",
            "pre_trade": pre,
            "order": None,
            "execution": None,
            "fill": None,
            "is_trade_instruction": False,
        }
    oms = _reg.get_adapter("oms").push(dict(order), context=ctx)
    ems = _reg.get_adapter("ems").push(dict(order), context=ctx)
    broker = _reg.get_adapter("broker").push(dict(order), context=ctx)
    return {
        "status": "ACCEPTED_SIM",
        "pre_trade": pre,
        "order": oms.as_dict(),
        "execution": ems.as_dict(),
        "fill": broker.as_dict(),
        "is_trade_instruction": False,
    }


def current_position(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    ctx = context or AdapterContext()
    pms = _reg.get_adapter("pms").pull(
        {
            "fund_id": snapshot.fund_id,
            "holdings": {p.security_code: p.market_value_base for p in snapshot.positions},
        },
        context=ctx,
    )
    return pms.as_dict()


def post_trade(
    snapshot: Any,
    order: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    proposed = apply_proposed_trade(snapshot, order)
    limits = _limits.evaluate(proposed, policy=policy)
    state = limits["state"]
    decision = "MONITOR"
    if state == "HARD_BREACH":
        decision = "ESCALATE"
    elif state == "BREACH":
        decision = "REVIEW"
    elif state == "WARNING":
        decision = "WATCH"
    return {
        "decision": decision,
        "state": state,
        "limit": limits,
        "proposed_positions": len(proposed.positions),
        "is_live": False,
        "is_trade_instruction": False,
    }
