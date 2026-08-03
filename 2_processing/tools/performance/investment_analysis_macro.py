"""Macro and market dynamics calculations."""
from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import (
    _correlation,
    _daily_returns,
    _index_history,
    _nav_history,
    _number,
    _return_between,
    _date_value,
)


async def compute_macro_market_dynamics(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    history = await _nav_history(db, fund_id, period_end, period_start)
    fund_points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    fund_returns = _daily_returns(fund_points)
    fund_vol = (
        statistics.stdev(fund_returns.values()) * math.sqrt(252) * 100.0
        if len(fund_returns) >= 2
        else None
    )
    if fund_vol is None:
        regime = "UNKNOWN"
    elif fund_vol >= 12:
        regime = "HIGH_VOL"
    elif fund_vol >= 6:
        regime = "MID_VOL"
    else:
        regime = "LOW_VOL"

    index_codes_result = await db.execute(
        text(
            """
            SELECT index_code, COUNT(*) AS observations
            FROM fsi.mktdata_index_quotes
            WHERE price_date BETWEEN :start AND :end
            GROUP BY index_code
            HAVING COUNT(*) >= 20
            ORDER BY observations DESC
            LIMIT 6
            """
        ),
        {"start": period_start, "end": period_end},
    )
    index_codes = [str(row.index_code) for row in index_codes_result]

    indicator_rows: list[dict[str, Any]] = []
    index_return_series: dict[str, dict[date, float]] = {}
    for code in index_codes:
        points = await _index_history(db, code, period_start, period_end)
        if len(points) < 2:
            continue
        returns = _daily_returns(points)
        index_return_series[code] = returns
        period_return = _return_between(points)
        annual_vol = statistics.stdev(returns.values()) * math.sqrt(252) * 100.0 if len(returns) >= 2 else None
        indicator_rows.append(
            {
                "index_code": code,
                "period_return_pct": period_return * 100.0 if period_return is not None else None,
                "annualized_volatility_pct": annual_vol,
                "sample_size": len(returns),
            }
        )

    pair_rows: list[dict[str, Any]] = []
    keys = list(index_return_series.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            corr = _correlation(index_return_series[keys[i]], index_return_series[keys[j]])
            if corr is not None:
                pair_rows.append(
                    {
                        "left": keys[i],
                        "right": keys[j],
                        "correlation": corr,
                    }
                )
    pair_rows.sort(key=lambda row: abs(_number(row["correlation"])), reverse=True)

    fund_index_corr = []
    for code, returns in index_return_series.items():
        corr = _correlation(fund_returns, returns)
        if corr is not None:
            fund_index_corr.append({"index_code": code, "correlation": corr})
    fund_index_corr.sort(key=lambda row: abs(_number(row["correlation"])), reverse=True)

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "fund_regime": {
            "annualized_volatility_pct": fund_vol,
            "regime": regime,
            "sample_size": len(fund_returns),
        },
        "macro_indicators": indicator_rows,
        "cross_asset_correlations": pair_rows[:20],
        "fund_vs_market_correlations": fund_index_corr,
    }
