"""Risk indicators calculations."""
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
    _equity_beta,
    _nav_history,
    _number,
    _return_between,
)


async def compute_risk_indicators(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """計算區間收益率、波動率、最大回撤、股票換手率和股票 Beta。"""
    history = await _nav_history(db, fund_id, period_end, period_start)
    points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    returns = list(_daily_returns(points).values())
    interval_return = _return_between(points)
    annualized_volatility = (
        statistics.stdev(returns) * math.sqrt(252) if len(returns) >= 2 else None
    )

    peak_value = -math.inf
    peak_date: date | None = None
    drawdown = 0.0
    drawdown_start: date | None = None
    drawdown_end: date | None = None
    for point_date, value in points:
        if value > peak_value:
            peak_value = value
            peak_date = point_date
        if peak_value > 0:
            current_drawdown = value / peak_value - 1.0
            if current_drawdown < drawdown:
                drawdown = current_drawdown
                drawdown_start = peak_date
                drawdown_end = point_date

    turnover_result = await db.execute(
        text(
            """
            WITH trades AS (
                SELECT SUM(CASE WHEN direction::text = 'BUY'
                                THEN ABS(COALESCE(amount_base_ccy, gross_amount)) ELSE 0 END) AS buy_amount,
                       SUM(CASE WHEN direction::text = 'SELL'
                                THEN ABS(COALESCE(amount_base_ccy, gross_amount)) ELSE 0 END) AS sell_amount
                FROM fsi.transact_stock
                WHERE port_id = :fund_id
                  AND trade_date BETWEEN :start AND :end
                  AND status::text = 'CONFIRMED'
            ), daily_balance AS (
                SELECT evaluate_date,
                       SUM(COALESCE(market_value_base, market_value)) AS market_value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id
                  AND evaluate_date BETWEEN :start AND :end
                GROUP BY evaluate_date
            )
            SELECT COALESCE(t.buy_amount, 0) AS buy_amount,
                   COALESCE(t.sell_amount, 0) AS sell_amount,
                   COALESCE(AVG(d.market_value), 0) AS average_equity_balance
            FROM trades t
            LEFT JOIN daily_balance d ON TRUE
            GROUP BY t.buy_amount, t.sell_amount
            """
        ),
        {"fund_id": fund_id, "start": period_start, "end": period_end},
    )
    turnover_row = dict(turnover_result.mappings().first() or {})
    buy_amount = _number(turnover_row.get("buy_amount"))
    sell_amount = _number(turnover_row.get("sell_amount"))
    average_balance = _number(turnover_row.get("average_equity_balance"))
    one_way_amount = min(buy_amount, sell_amount)
    period_turnover = one_way_amount / average_balance if average_balance else None
    calendar_days = max((period_end - period_start).days + 1, 1)
    annualized_turnover = period_turnover * 365 / calendar_days if period_turnover is not None else None

    benchmark_id = await _benchmark_id(db, fund_id, period_end)
    equity_beta = await _equity_beta(db, fund_id, benchmark_id, period_start, period_end)

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "interval_return_pct": interval_return * 100.0 if interval_return is not None else None,
        "annualized_volatility_pct": annualized_volatility * 100.0 if annualized_volatility is not None else None,
        "max_drawdown_pct": drawdown * 100.0 if points else None,
        "max_drawdown_start": drawdown_start,
        "max_drawdown_end": drawdown_end,
        "sample_size": len(returns),
        "equity_turnover": {
            "buy_amount": buy_amount,
            "sell_amount": sell_amount,
            "average_equity_balance": average_balance,
            "period_turnover_pct": period_turnover * 100.0 if period_turnover is not None else None,
            "annualized_turnover_pct": annualized_turnover * 100.0 if annualized_turnover is not None else None,
            "method": "單邊換手率=min(買入額,賣出額)/區間日均股票餘額",
        },
        "equity_beta": equity_beta,
    }
