"""Pre-trade risk budget calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..risk.rule_limits import load_effective_pretrade_limits
from .investment_analysis_common import _number


async def compute_pretrade_risk_budget(
    fund_id: str,
    as_of_date: date,
    trade_amount: float,
    trade_side: str,
    asset_class: str,
    duration_years: float,
    issuer_name: str,
    db: AsyncSession,
) -> dict[str, Any]:
    nav_result = await db.execute(
        text(
            """
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            ORDER BY evaluate_date DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    nav = _number(nav_result.scalar_one_or_none())

    bonds_result = await db.execute(
        text(
            """
            SELECT COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
                   COALESCE(market_value_base, market_value, 0) AS market_value,
                   COALESCE(duration, 0) AS duration
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    bonds = [dict(row) for row in bonds_result.mappings().all()]
    total_bond_mv = sum(_number(row["market_value"]) for row in bonds)
    current_duration_numerator = sum(_number(row["market_value"]) * _number(row["duration"]) for row in bonds)
    current_duration = current_duration_numerator / total_bond_mv if total_bond_mv else 0.0

    sign = 1.0 if trade_side.upper() == "BUY" else -1.0
    signed_trade = sign * abs(trade_amount)
    bond_trade_amount = signed_trade if asset_class.upper().startswith("BOND") else 0.0
    projected_bond_mv = max(total_bond_mv + bond_trade_amount, 0.0)
    projected_duration_numerator = current_duration_numerator + bond_trade_amount * duration_years
    projected_duration = (
        projected_duration_numerator / projected_bond_mv if projected_bond_mv else 0.0
    )

    issuer_mv: dict[str, float] = defaultdict(float)
    for row in bonds:
        issuer_mv[str(row["issuer_name"])] += _number(row["market_value"])
    current_issuer_mv = issuer_mv.get(issuer_name, 0.0)
    projected_issuer_mv = max(current_issuer_mv + bond_trade_amount, 0.0)
    current_issuer_pct = current_issuer_mv / nav * 100.0 if nav else None
    projected_issuer_pct = projected_issuer_mv / nav * 100.0 if nav else None

    tracking_error_proxy = abs(signed_trade) / nav * 100.0 if nav else None
    projected_dv01 = projected_bond_mv * projected_duration * 0.0001
    current_dv01 = total_bond_mv * current_duration * 0.0001

    configured_limits, applied_rules = await load_effective_pretrade_limits(
        db=db,
        fund_id=fund_id,
        as_of_date=as_of_date,
        asset_class=asset_class,
        trade_side=trade_side,
    )
    duration_limit = configured_limits["duration_years"]
    issuer_limit_pct = configured_limits["issuer_pct_nav"]
    te_limit_pct = configured_limits["tracking_error_proxy_pct"]
    breaches = []
    if projected_duration > duration_limit:
        breaches.append(f"組合久期超限（>{duration_limit:.1f}年）")
    if projected_issuer_pct is not None and projected_issuer_pct > issuer_limit_pct:
        breaches.append(f"發行人集中度超限（>{issuer_limit_pct:.1f}% NAV）")
    if tracking_error_proxy is not None and tracking_error_proxy > te_limit_pct:
        breaches.append(f"單筆交易衝擊超限（>{te_limit_pct:.1f}% NAV）")

    decision = "ALLOW"
    if breaches:
        decision = "ALLOW_WITH_WARNING" if len(breaches) == 1 else "BLOCK"

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "trade": {
            "trade_amount": trade_amount,
            "trade_side": trade_side.upper(),
            "asset_class": asset_class,
            "duration_years": duration_years,
            "issuer_name": issuer_name,
        },
        "current": {
            "net_asset": nav,
            "bond_market_value": total_bond_mv,
            "duration_years": current_duration,
            "issuer_pct_nav": current_issuer_pct,
            "portfolio_dv01": current_dv01,
        },
        "projected": {
            "bond_market_value": projected_bond_mv,
            "duration_years": projected_duration,
            "issuer_pct_nav": projected_issuer_pct,
            "portfolio_dv01": projected_dv01,
            "tracking_error_proxy_pct": tracking_error_proxy,
        },
        "limits": {
            "duration_years": duration_limit,
            "issuer_pct_nav": issuer_limit_pct,
            "tracking_error_proxy_pct": te_limit_pct,
        },
        "applied_rules": applied_rules,
        "breach_flags": breaches,
        "decision": decision,
    }
