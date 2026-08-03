"""Liquidity stress testing calculations."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _daily_returns, _date_value, _nav_history, _number


async def compute_liquidity_stress_testing(
    fund_id: str,
    as_of_date: date,
    redemption_pct: float,
    rate_shock_bps: float,
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

    assets_result = await db.execute(
        text(
            """
            SELECT asset_class::text AS asset_class,
                   SUM(COALESCE(market_value_base, market_value, 0)) AS market_value
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            GROUP BY asset_class::text
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    assets = [dict(row) for row in assets_result.mappings().all()]
    liquidation_days = {
        "CASH": 0,
        "DEPOSIT": 1,
        "REPO": 1,
        "REV_REPO": 1,
        "CD": 3,
        "BOND_GOVT": 5,
        "CP": 5,
        "BOND_CORP": 10,
        "BOND_CONVERT": 12,
        "BOND_ABS": 15,
        "STOCK": 7,
        "FUND_PUBLIC": 7,
        "FUND_ETF": 3,
        "OTHER": 20,
    }

    ladders = []
    for row in assets:
        mv = _number(row["market_value"])
        ladders.append(
            {
                "asset_class": str(row["asset_class"]),
                "market_value": mv,
                "ttl_days": liquidation_days.get(str(row["asset_class"]), 20),
            }
        )
    ladders.sort(key=lambda row: row["ttl_days"])

    cumulative = 0.0
    for row in ladders:
        cumulative += row["market_value"]
        row["cumulative_market_value"] = cumulative
        row["cumulative_pct_nav"] = cumulative / nav * 100.0 if nav else None

    def _ttl_for_target(target_pct: float) -> int | None:
        if not nav:
            return None
        target_mv = nav * target_pct / 100.0
        running = 0.0
        for item in ladders:
            running += item["market_value"]
            if running >= target_mv:
                return int(item["ttl_days"])
        return None

    ttl_snapshot = {
        "ttl_10pct_days": _ttl_for_target(10),
        "ttl_25pct_days": _ttl_for_target(25),
        "ttl_50pct_days": _ttl_for_target(50),
    }

    bonds_result = await db.execute(
        text(
            """
            SELECT COALESCE(market_value_base, market_value, 0) AS market_value,
                   COALESCE(duration, 0) AS duration
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    rate_shock = rate_shock_bps / 10000.0
    stressed_bond_loss = sum(
        _number(row.market_value) * _number(row.duration) * rate_shock for row in bonds_result
    )

    redemption_amount = nav * redemption_pct / 100.0 if nav else 0.0
    liquid_within_7d = sum(item["market_value"] for item in ladders if item["ttl_days"] <= 7)
    liquidity_coverage = liquid_within_7d / redemption_amount if redemption_amount else None
    illiquid_part = max(redemption_amount - liquid_within_7d, 0.0)
    redemption_impact_cost = illiquid_part * 0.002

    history = await _nav_history(db, fund_id, as_of_date, as_of_date - timedelta(days=730))
    nav_points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    daily = _daily_returns(nav_points)
    sorted_daily = sorted(daily.values())
    worst_1d = sorted_daily[0] * 100.0 if sorted_daily else None
    worst_5d = None
    if len(sorted_daily) >= 5:
        worst_5d = sum(sorted_daily[:5]) * 100.0

    stressed_nav = nav - stressed_bond_loss - redemption_impact_cost if nav else None
    breaches = []
    if liquidity_coverage is not None and liquidity_coverage < 1:
        breaches.append("7日流動性覆蓋不足")
    if ttl_snapshot["ttl_50pct_days"] is not None and ttl_snapshot["ttl_50pct_days"] > 7:
        breaches.append("50%資產變現超過7天")

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "net_asset": nav,
        "redemption_pct": redemption_pct,
        "rate_shock_bps": rate_shock_bps,
        "liquidity_ladder": ladders,
        "ttl_snapshot": ttl_snapshot,
        "stress_summary": {
            "redemption_amount": redemption_amount,
            "liquid_within_7d": liquid_within_7d,
            "liquidity_coverage_ratio": liquidity_coverage,
            "stressed_bond_loss": stressed_bond_loss,
            "redemption_impact_cost": redemption_impact_cost,
            "projected_stressed_nav": stressed_nav,
        },
        "historical_stress": {
            "worst_1d_return_pct": worst_1d,
            "worst_5d_cumulative_return_pct": worst_5d,
            "sample_size": len(sorted_daily),
        },
        "breach_flags": breaches,
    }
