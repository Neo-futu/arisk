"""Rates and credit sensitivity calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _date_value, _number


async def compute_rates_credit_sensitivity(
    fund_id: str,
    as_of_date: date,
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
            SELECT security_code,
                   security_name,
                   COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
                   COALESCE(debt_rating, issuer_rating, 'NR') AS rating,
                   maturity_date,
                   COALESCE(duration, 0) AS duration,
                   COALESCE(ytm, 0) AS ytm,
                   COALESCE(market_value_base, market_value, 0) AS market_value
            FROM fsi.balance_bond
            WHERE port_id = :fund_id
              AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    bonds = [dict(row) for row in bonds_result.mappings().all()]
    total_bond_mv = sum(_number(item["market_value"]) for item in bonds)
    weighted_duration = (
        sum(_number(item["market_value"]) * _number(item["duration"]) for item in bonds) / total_bond_mv
        if total_bond_mv
        else None
    )

    krd_buckets: dict[str, float] = {"1M": 0.0, "3M": 0.0, "6M": 0.0, "1Y": 0.0, "1Y+": 0.0}
    issuer_mv: dict[str, float] = defaultdict(float)
    rating_mv: dict[str, float] = defaultdict(float)
    portfolio_dv01 = 0.0
    portfolio_cs01 = 0.0
    for item in bonds:
        mv = _number(item["market_value"])
        duration_years = _number(item["duration"])
        maturity_date = item.get("maturity_date")
        days_to_maturity = 9999
        if maturity_date is not None:
            try:
                days_to_maturity = max((_date_value(maturity_date) - as_of_date).days, 0)
            except Exception:
                days_to_maturity = 9999

        if days_to_maturity <= 30:
            bucket = "1M"
        elif days_to_maturity <= 90:
            bucket = "3M"
        elif days_to_maturity <= 180:
            bucket = "6M"
        elif days_to_maturity <= 365:
            bucket = "1Y"
        else:
            bucket = "1Y+"
        krd_buckets[bucket] += mv * duration_years

        issuer_mv[str(item["issuer_name"])] += mv
        rating_mv[str(item["rating"])] += mv
        portfolio_dv01 += mv * duration_years * 0.0001
        # 沒有完整 spread duration 時，使用 duration 的 80% 作保守代理
        portfolio_cs01 += mv * duration_years * 0.8 * 0.0001

    issuer_rows = [
        {
            "issuer": issuer,
            "market_value": value,
            "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
        }
        for issuer, value in issuer_mv.items()
    ]
    issuer_rows.sort(key=lambda row: row["market_value"], reverse=True)
    hhi = sum((row["weight_pct"] / 100.0) ** 2 for row in issuer_rows) * 10000 if issuer_rows else 0.0

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "net_asset": nav,
        "total_bond_market_value": total_bond_mv,
        "bond_exposure_pct_nav": total_bond_mv / nav * 100.0 if nav else None,
        "weighted_duration_years": weighted_duration,
        "portfolio_dv01": portfolio_dv01,
        "portfolio_cs01": portfolio_cs01,
        "krd_buckets": [
            {
                "bucket": key,
                "duration_weighted_mv": value,
                "weight_pct_bond": value / sum(krd_buckets.values()) * 100.0 if sum(krd_buckets.values()) else 0.0,
            }
            for key, value in krd_buckets.items()
        ],
        "issuer_concentration": {
            "hhi": hhi,
            "top_issuers": issuer_rows[:10],
        },
        "rating_distribution": [
            {
                "rating": rating,
                "market_value": value,
                "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
            }
            for rating, value in sorted(rating_mv.items(), key=lambda item: item[1], reverse=True)
        ],
        "bond_count": len(bonds),
    }
