"""Shared helpers for investment analysis calculations."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _number(value: Any, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _date_value(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _daily_returns(points: list[tuple[date, float]]) -> dict[date, float]:
    result: dict[date, float] = {}
    for (previous_date, previous), (current_date, current) in zip(points, points[1:]):
        del previous_date
        if previous:
            result[current_date] = current / previous - 1.0
    return result


def _return_between(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 2 or not points[0][1]:
        return None
    return points[-1][1] / points[0][1] - 1.0


def _beta(asset_returns: dict[date, float], benchmark_returns: dict[date, float]) -> tuple[float | None, int]:
    common_dates = sorted(set(asset_returns) & set(benchmark_returns))
    if len(common_dates) < 2:
        return None, len(common_dates)
    assets = [asset_returns[item] for item in common_dates]
    benchmark = [benchmark_returns[item] for item in common_dates]
    benchmark_variance = statistics.variance(benchmark)
    if math.isclose(benchmark_variance, 0.0):
        return None, len(common_dates)
    covariance = sum(
        (asset - statistics.mean(assets)) * (index - statistics.mean(benchmark))
        for asset, index in zip(assets, benchmark)
    ) / (len(common_dates) - 1)
    return covariance / benchmark_variance, len(common_dates)


def _correlation(series_a: dict[date, float], series_b: dict[date, float]) -> float | None:
    common_dates = sorted(set(series_a) & set(series_b))
    if len(common_dates) < 2:
        return None
    a_values = [series_a[item] for item in common_dates]
    b_values = [series_b[item] for item in common_dates]
    std_a = statistics.stdev(a_values)
    std_b = statistics.stdev(b_values)
    if math.isclose(std_a, 0.0) or math.isclose(std_b, 0.0):
        return None
    mean_a = statistics.mean(a_values)
    mean_b = statistics.mean(b_values)
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a_values, b_values)) / (len(common_dates) - 1)
    return covariance / (std_a * std_b)


async def _nav_history(
    db: AsyncSession,
    fund_id: str,
    end: date,
    start: date | None = None,
) -> list[dict[str, Any]]:
    start_filter = "AND evaluate_date >= :start" if start else ""
    rows = await db.execute(
        text(
            f"""
            SELECT evaluate_date,
                   MAX(COALESCE(acc_unit_nav, unit_nav)) AS nav,
                   MAX(net_asset) AS net_asset,
                   MAX(day_return) AS day_return
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id
              AND evaluate_date <= :end
              {start_filter}
            GROUP BY evaluate_date
            ORDER BY evaluate_date
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    return [dict(row) for row in rows.mappings().all() if row["nav"] is not None]


def _nav_daily_returns(history: list[dict[str, Any]]) -> dict[date, float]:
    """日收益率：優先使用庫內 day_return（貨基 unit_nav≈1 時更準），否則用 NAV 比。"""
    result: dict[date, float] = {}
    previous_nav: float | None = None
    for row in history:
        point_date = _date_value(row["evaluate_date"])
        nav = _number(row.get("nav"))
        stored = row.get("day_return")
        if stored is not None:
            result[point_date] = _number(stored)
        elif previous_nav:
            result[point_date] = nav / previous_nav - 1.0
        previous_nav = nav
    return result


async def _latest_nav_date(
    db: AsyncSession,
    fund_id: str,
    as_of: date,
) -> date | None:
    """最近一筆 NAV 估值日（≤ as_of）。"""
    result = await db.execute(
        text(
            """
            SELECT MAX(evaluate_date) AS value
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id
              AND evaluate_date <= :as_of
              AND COALESCE(acc_unit_nav, unit_nav) IS NOT NULL
            """
        ),
        {"fund_id": fund_id, "as_of": as_of},
    )
    value = result.scalar_one_or_none()
    return _date_value(value) if value is not None else None


async def _resolve_nav_period(
    db: AsyncSession,
    fund_id: str,
    period_start: date,
    period_end: date,
) -> tuple[date, date, date] | None:
    """把請求區間對齊到庫內實際有 NAV 的窗口。

    返回 (effective_start, effective_end, latest_nav_date)；
    若 as_of 之前完全無 NAV，返回 None。
    """
    latest = await _latest_nav_date(db, fund_id, period_end)
    if latest is None:
        return None
    effective_end = min(period_end, latest)
    span_days = max((period_end - period_start).days, 0)
    effective_start = effective_end - timedelta(days=span_days)
    # 若仍無點（極端缺口），放寬起點到 earliest available ≤ end
    probe = await _nav_history(db, fund_id, effective_end, effective_start)
    if not probe:
        history = await _nav_history(db, fund_id, effective_end, None)
        if not history:
            return None
        # 取結束日前、長度約等於請求窗口的可用序列
        dates = [_date_value(row["evaluate_date"]) for row in history]
        effective_start = dates[0]
        for item in dates:
            if item >= effective_end - timedelta(days=span_days):
                effective_start = item
                break
    return effective_start, effective_end, latest


def _performance_periods(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(history) < 2:
        return []
    points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    end_date, end_nav = points[-1]
    targets: list[tuple[str, date | None]] = [
        ("1日", None),
        ("1月", end_date - timedelta(days=30)),
        ("3月", end_date - timedelta(days=90)),
        ("年初至今", date(end_date.year, 1, 1) - timedelta(days=1)),
        ("1年", end_date - timedelta(days=365)),
        ("成立以來", points[0][0]),
    ]
    periods: list[dict[str, Any]] = []
    for label, target in targets:
        if label == "1日":
            start_date, start_nav = points[-2]
        elif label == "成立以來":
            start_date, start_nav = points[0]
        else:
            candidates = [point for point in points if point[0] <= target]  # type: ignore[operator]
            if not candidates:
                continue
            start_date, start_nav = candidates[-1]
        if not start_nav:
            continue
        periods.append(
            {
                "period": label,
                "start_date": start_date,
                "end_date": end_date,
                "return_pct": (end_nav / start_nav - 1.0) * 100.0,
            }
        )
    return periods


async def _benchmark_id(db: AsyncSession, fund_id: str, as_of_date: date) -> str | None:
    result = await db.execute(
        text(
            """
            SELECT benchmark_id
            FROM fsi.para_portfolio_benchmark
            WHERE port_id = :fund_id
              AND begin_date <= :as_of_date
              AND (end_date IS NULL OR end_date >= :as_of_date)
            ORDER BY (benchmark_role = 'PRIMARY') DESC, weight_pct DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    return result.scalar_one_or_none()


async def _index_history(
    db: AsyncSession,
    benchmark_id: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    result = await db.execute(
        text(
            """
            SELECT price_date, close_price
            FROM fsi.mktdata_index_quotes
            WHERE index_code = :benchmark_id
              AND price_date BETWEEN :start AND :end
            ORDER BY price_date
            """
        ),
        {"benchmark_id": benchmark_id, "start": start, "end": end},
    )
    return [(_date_value(row[0]), _number(row[1])) for row in result.all()]


async def _equity_beta(
    db: AsyncSession,
    fund_id: str,
    benchmark_id: str | None,
    start: date,
    end: date,
) -> dict[str, Any]:
    if not benchmark_id:
        return {"value": None, "benchmark_id": None, "sample_size": 0, "constituents": []}

    quote_result = await db.execute(
        text(
            """
            WITH latest_date AS (
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id AND evaluate_date <= :end
            ), holdings AS (
                SELECT security_code, security_name,
                       COALESCE(market_value_base, market_value) AS market_value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id
                  AND evaluate_date = (SELECT value FROM latest_date)
            )
            SELECT q.price_date, q.security_code, q.close_price,
                   h.security_name, h.market_value
            FROM fsi.mktdata_quotes q
            JOIN holdings h ON h.security_code = q.security_code
            WHERE q.price_type = 'CLOSE'
              AND q.price_date BETWEEN :start AND :end
            ORDER BY q.security_code, q.price_date
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    quote_rows = [dict(row) for row in quote_result.mappings().all()]
    benchmark_points = await _index_history(db, benchmark_id, start, end)
    benchmark_returns = _daily_returns(benchmark_points)

    by_security: dict[str, list[tuple[date, float]]] = defaultdict(list)
    metadata: dict[str, tuple[str, float]] = {}
    for row in quote_rows:
        code = str(row["security_code"])
        by_security[code].append((_date_value(row["price_date"]), _number(row["close_price"])))
        metadata[code] = (str(row.get("security_name") or code), _number(row.get("market_value")))

    constituents: list[dict[str, Any]] = []
    weighted_beta = 0.0
    usable_weight = 0.0
    total_market_value = sum(value[1] for value in metadata.values())
    max_sample_size = 0
    for code, points in by_security.items():
        beta_value, sample_size = _beta(_daily_returns(points), benchmark_returns)
        max_sample_size = max(max_sample_size, sample_size)
        if beta_value is None:
            continue
        name, market_value = metadata[code]
        weight = market_value / total_market_value if total_market_value else 0.0
        weighted_beta += beta_value * weight
        usable_weight += weight
        constituents.append(
            {
                "security_code": code,
                "security_name": name,
                "weight_pct": weight * 100.0,
                "beta": beta_value,
                "sample_size": sample_size,
            }
        )

    constituents.sort(key=lambda row: row["weight_pct"], reverse=True)
    return {
        "value": weighted_beta / usable_weight if usable_weight else None,
        "benchmark_id": benchmark_id,
        "sample_size": max_sample_size,
        "constituents": constituents[:10],
    }
