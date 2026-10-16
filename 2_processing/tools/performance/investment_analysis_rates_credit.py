"""Rates and credit sensitivity calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _date_value, _number

# 投资级（IG）：BBB- / Baa3 及以上；其余含 NR 视为低于投资级
_INVESTMENT_GRADE = {
    "AAA+", "AAA", "AAA-", "AA+", "AA", "AA-",
    "A+", "A", "A-", "BBB+", "BBB", "BBB-",
    "AA1", "AA2", "AA3", "A1", "A2", "A3",
    "BAA1", "BAA2", "BAA3", "BAA",
}
_RATING_ORDER = [
    "AAA+", "AAA", "AAA-", "AA+", "AA", "AA-",
    "A+", "A", "A-", "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-", "B+", "B", "B-",
    "CCC", "CC", "C", "D", "NR",
]


def _normalize_rating(raw: object) -> str:
    text_v = str(raw or "NR").strip().upper().replace(" ", "")
    return text_v or "NR"


def _is_investment_grade(rating: str) -> bool:
    r = _normalize_rating(rating)
    if r in _INVESTMENT_GRADE:
        return True
    if r in {"AAA", "AA", "A", "BAA", "BBB"}:
        return True
    return False


def _rating_sort_key(rating: str) -> tuple[int, str]:
    r = _normalize_rating(rating)
    try:
        return (_RATING_ORDER.index(r), r)
    except ValueError:
        return (len(_RATING_ORDER), r)


def _build_rating_distribution(
    rating_mv: dict[str, float],
    total_bond_mv: float,
) -> dict[str, Any]:
    rows = [
        {
            "rating": rating,
            "market_value": value,
            "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
            "is_investment_grade": _is_investment_grade(rating),
        }
        for rating, value in sorted(rating_mv.items(), key=lambda item: _rating_sort_key(item[0]))
    ]
    ig_mv = sum(v for r, v in rating_mv.items() if _is_investment_grade(r))
    below_ig_mv = total_bond_mv - ig_mv
    return {
        "distribution": rows,
        "investment_grade_pct": (ig_mv / total_bond_mv * 100.0) if total_bond_mv else None,
        "below_investment_grade_pct": (below_ig_mv / total_bond_mv * 100.0) if total_bond_mv else None,
    }


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
                   issuer_rating,
                   debt_rating,
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
    blended_rating_mv: dict[str, float] = defaultdict(float)
    issuer_rating_mv: dict[str, float] = defaultdict(float)
    debt_rating_mv: dict[str, float] = defaultdict(float)
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
        blended_rating_mv[_normalize_rating(item["rating"])] += mv
        issuer_rating_mv[_normalize_rating(item.get("issuer_rating"))] += mv
        debt_rating_mv[_normalize_rating(item.get("debt_rating"))] += mv
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

    blended = _build_rating_distribution(blended_rating_mv, total_bond_mv)
    issuer_rt = _build_rating_distribution(issuer_rating_mv, total_bond_mv)
    debt_rt = _build_rating_distribution(debt_rating_mv, total_bond_mv)

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
        # 兼容旧前端：合成评级（债项优先，缺省主体）
        "rating_distribution": blended["distribution"],
        "investment_grade_pct": blended["investment_grade_pct"],
        "below_investment_grade_pct": blended["below_investment_grade_pct"],
        # 主体 / 债项分列
        "issuer_rating_distribution": issuer_rt["distribution"],
        "debt_rating_distribution": debt_rt["distribution"],
        "issuer_investment_grade_pct": issuer_rt["investment_grade_pct"],
        "issuer_below_investment_grade_pct": issuer_rt["below_investment_grade_pct"],
        "debt_investment_grade_pct": debt_rt["investment_grade_pct"],
        "debt_below_investment_grade_pct": debt_rt["below_investment_grade_pct"],
        "bond_count": len(bonds),
    }
