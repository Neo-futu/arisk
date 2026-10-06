"""Time-series calculations for investment analysis charts."""
from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import (
    _benchmark_id,
    _daily_returns,
    _date_value,
    _index_history,
    _nav_daily_returns,
    _nav_history,
    _number,
    _resolve_nav_period,
)


async def compute_portfolio_overview_timeseries(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    history = await _nav_history(db, fund_id, period_end, period_start)
    if not history:
        return {
            "fund_id": fund_id,
            "period_start": period_start,
            "period_end": period_end,
            "points": [],
        }

    start_nav = _number(history[0].get("nav"))
    previous_nav: float | None = None
    points: list[dict[str, Any]] = []
    for row in history:
        nav = _number(row.get("nav"))
        daily_return = (nav / previous_nav - 1.0) * 100.0 if previous_nav else None
        cumulative_return = (nav / start_nav - 1.0) * 100.0 if start_nav else None
        points.append(
            {
                "date": _date_value(row["evaluate_date"]),
                "nav": nav,
                "net_asset": _number(row.get("net_asset")) if row.get("net_asset") is not None else None,
                "daily_return_pct": daily_return,
                "cumulative_return_pct": cumulative_return,
            }
        )
        previous_nav = nav

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "points": points,
    }


async def compute_risk_indicator_timeseries(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    resolved = await _resolve_nav_period(db, fund_id, period_start, period_end)
    if resolved is None:
        return {
            "fund_id": fund_id,
            "period_start": period_start,
            "period_end": period_end,
            "resolved_period_start": None,
            "resolved_period_end": None,
            "data_as_of": None,
            "points": [],
            "message": "指定結束日及之前無可用 NAV 數據",
        }

    effective_start, effective_end, latest_nav = resolved
    history = await _nav_history(db, fund_id, effective_end, effective_start)
    nav_points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    if not nav_points:
        return {
            "fund_id": fund_id,
            "period_start": period_start,
            "period_end": period_end,
            "resolved_period_start": effective_start,
            "resolved_period_end": effective_end,
            "data_as_of": latest_nav,
            "points": [],
            "message": "對齊後窗口仍無 NAV 點",
        }

    daily_returns = _nav_daily_returns(history)
    start_nav = nav_points[0][1]
    peak_nav = -math.inf
    rolling_window = 20
    return_points = list(daily_returns.items())
    points: list[dict[str, Any]] = []

    for index, (point_date, nav) in enumerate(nav_points):
        if nav > peak_nav:
            peak_nav = nav
        drawdown_pct = (nav / peak_nav - 1.0) * 100.0 if peak_nav > 0 else None

        # return_points[i] 對應 nav_points[i+1] 當日收益；取截至當日的窗口
        end_idx = index  # 不含當前 nav 索引之外的收益條數上限
        start_idx = max(0, end_idx - rolling_window)
        history_slice = [value for _, value in return_points[start_idx:end_idx]]
        rolling_volatility = None
        rolling_var = None
        if len(history_slice) >= 2:
            rolling_volatility = statistics.stdev(history_slice) * math.sqrt(252) * 100.0
        if len(history_slice) >= 5:
            sorted_returns = sorted(history_slice)
            quantile_index = max(0, math.ceil(len(sorted_returns) * 0.05) - 1)
            rolling_var = abs(sorted_returns[quantile_index]) * 100.0

        daily_return_pct = daily_returns.get(point_date)
        cumulative_return_pct = (nav / start_nav - 1.0) * 100.0 if start_nav else None
        points.append(
            {
                "date": point_date,
                "nav": nav,
                "daily_return_pct": daily_return_pct * 100.0 if daily_return_pct is not None else None,
                "cumulative_return_pct": cumulative_return_pct,
                "rolling_volatility_pct": rolling_volatility,
                "drawdown_pct": drawdown_pct,
                "rolling_var_95_pct": rolling_var,
            }
        )

    message = None
    if effective_end != period_end or effective_start != period_start:
        message = (
            f"請求區間 {period_start}~{period_end} 已對齊到庫內 NAV 窗口 "
            f"{effective_start}~{effective_end}（最近數據日 {latest_nav}）"
        )

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "resolved_period_start": effective_start,
        "resolved_period_end": effective_end,
        "data_as_of": latest_nav,
        "points": points,
        "message": message,
    }


async def compute_performance_attribution_timeseries(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    history = await _nav_history(db, fund_id, period_end, period_start)
    nav_points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    fund_returns = _daily_returns(nav_points)
    benchmark_id = await _benchmark_id(db, fund_id, period_end)
    benchmark_points = await _index_history(db, benchmark_id, period_start, period_end) if benchmark_id else []
    benchmark_returns = _daily_returns(benchmark_points)

    cumulative_points: list[dict[str, Any]] = []
    cumulative_fund = 1.0
    cumulative_benchmark = 1.0
    for point_date, _ in nav_points[1:]:
        fund_return = fund_returns.get(point_date, 0.0)
        benchmark_return = benchmark_returns.get(point_date, 0.0)
        cumulative_fund *= 1.0 + fund_return
        cumulative_benchmark *= 1.0 + benchmark_return
        cumulative_points.append(
            {
                "date": point_date,
                "fund_cumulative_return_pct": (cumulative_fund - 1.0) * 100.0,
                "benchmark_cumulative_return_pct": (cumulative_benchmark - 1.0) * 100.0,
                "active_cumulative_return_pct": (cumulative_fund - cumulative_benchmark) * 100.0,
            }
        )

    pnl_result = await db.execute(
        text(
            """
            SELECT evaluate_date,
                   SUM(COALESCE(net_pnl_base, net_pnl, 0)) AS net_pnl
            FROM fsi.transact_pnl_item
            WHERE port_id = :fund_id
              AND evaluate_date BETWEEN :start AND :end
            GROUP BY evaluate_date
            ORDER BY evaluate_date
            """
        ),
        {"fund_id": fund_id, "start": period_start, "end": period_end},
    )
    pnl_rows = [dict(row) for row in pnl_result.mappings().all()]
    start_net_asset = _number(history[0].get("net_asset")) if history else 0.0
    pnl_points = [
        {
            "date": _date_value(row["evaluate_date"]),
            "net_pnl": _number(row.get("net_pnl")),
            "contribution_pct": (_number(row.get("net_pnl")) / start_net_asset * 100.0) if start_net_asset else None,
        }
        for row in pnl_rows
    ]

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "benchmark_id": benchmark_id,
        "cumulative_points": cumulative_points,
        "pnl_points": pnl_points,
    }