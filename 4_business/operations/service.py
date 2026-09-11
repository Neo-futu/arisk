"""Operations: Valuation, NAV, PnL, Fund Accounting, Custodian, Fund Admin.

External books are read only through 5_integrations adapters.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

_engine = import_module("3_riskengine")
_reg = import_module("5_integrations.registry")
_base = import_module("5_integrations.base")
_valuation = import_module("3_riskengine.valuation")

AdapterContext = _base.AdapterContext
RiskEngine = _engine.RiskEngine


def valuation(snapshot: Any) -> dict[str, Any]:
    priced = _valuation.price(snapshot)
    return {
        "base_pv": priced.base_pv,
        "engine": priced.context.get("engine"),
        "source": "riskengine",
    }


def nav(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    ctx = context or AdapterContext()
    admin = _reg.get_adapter("fund_admin").pull(
        {"fund_id": snapshot.fund_id, "nav": snapshot.net_asset},
        context=ctx,
    )
    return {"riskengine_nav": snapshot.net_asset, "fund_admin": admin.as_dict()}


def pnl(snapshot: Any, shocks: Any = ()) -> dict[str, Any]:
    report = RiskEngine().bind(snapshot).valuation().pnl(shocks)
    return report if isinstance(report, dict) else {"pnl": getattr(report, "pnl", None)}


def fund_accounting(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    ctx = context or AdapterContext()
    books = _reg.get_adapter("accounting").pull({"fund_id": snapshot.fund_id}, context=ctx)
    return books.as_dict()


def custodian(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    ctx = context or AdapterContext()
    cash = next((p.market_value_base for p in snapshot.positions if p.asset_class == "CASH"), 0.0)
    custody = _reg.get_adapter("custodian").pull(
        {"fund_id": snapshot.fund_id, "cash": cash},
        context=ctx,
    )
    return custody.as_dict()


def fund_administrator(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    return nav(snapshot, context=context)


def pack(snapshot: Any, *, context: AdapterContext | None = None) -> dict[str, Any]:
    ctx = context or AdapterContext()
    return {
        "valuation": valuation(snapshot),
        "nav": nav(snapshot, context=ctx),
        "pnl": pnl(snapshot),
        "fund_accounting": fund_accounting(snapshot, context=ctx),
        "custodian": custodian(snapshot, context=ctx),
        "fund_admin": fund_administrator(snapshot, context=ctx),
    }
