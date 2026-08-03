"""Factor and behavioral risk calculations."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _daily_returns, _date_value, _number, _return_between


async def compute_factor_behavior_risk(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    holdings_result = await db.execute(
        text(
            """
            WITH latest_date AS (
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_stock
                WHERE port_id = :fund_id AND evaluate_date <= :end
            )
            SELECT security_code,
                   COALESCE(security_name, security_code) AS security_name,
                   COALESCE(sector, '未分類') AS sector,
                   COALESCE(quantity, 0) AS quantity,
                   COALESCE(market_value_base, market_value, 0) AS market_value,
                   COALESCE(weight_pct, 0) AS weight_pct
            FROM fsi.balance_stock
            WHERE port_id = :fund_id
              AND evaluate_date = (SELECT value FROM latest_date)
            """
        ),
        {"fund_id": fund_id, "end": period_end},
    )
    holdings = [dict(row) for row in holdings_result.mappings().all()]

    quote_result = await db.execute(
        text(
            """
            SELECT price_date, security_code, close_price, COALESCE(volume, 0) AS volume
            FROM fsi.mktdata_quotes
            WHERE price_type = 'CLOSE'
              AND price_date BETWEEN :start AND :end
              AND security_code = ANY(:codes)
            ORDER BY security_code, price_date
            """
        ),
        {"start": period_start, "end": period_end, "codes": [item["security_code"] for item in holdings] or ["__NONE__"]},
    )
    quote_rows = [dict(row) for row in quote_result.mappings().all()]

    prices_by_security: dict[str, list[tuple[date, float]]] = defaultdict(list)
    avg_volume_by_security: dict[str, list[float]] = defaultdict(list)
    for row in quote_rows:
        code = str(row["security_code"])
        prices_by_security[code].append((_date_value(row["price_date"]), _number(row["close_price"])))
        avg_volume_by_security[code].append(_number(row["volume"]))

    total_mv = sum(_number(item["market_value"]) for item in holdings)
    momentum_exposure = 0.0
    low_vol_exposure = 0.0
    size_exposure = 0.0
    coverage_weight = 0.0

    crowding_rows = []
    sector_weight: dict[str, float] = defaultdict(float)
    for item in holdings:
        code = str(item["security_code"])
        mv = _number(item["market_value"])
        weight = mv / total_mv if total_mv else 0.0
        sector_weight[str(item["sector"])] += weight
        points = prices_by_security.get(code, [])
        returns = _daily_returns(points)
        period_return = _return_between(points) if points else None
        vol = statistics.stdev(returns.values()) if len(returns) >= 2 else None
        if period_return is not None and vol is not None:
            momentum_exposure += period_return * weight
            low_vol_exposure += (1.0 / (1.0 + vol)) * weight
            size_exposure += math.log(max(mv, 1.0)) * weight
            coverage_weight += weight

        avg_volume = statistics.mean(avg_volume_by_security.get(code, [0.0])) if avg_volume_by_security.get(code) else 0.0
        quantity = _number(item.get("quantity"))
        crowding_ratio = quantity / avg_volume if avg_volume else None
        crowding_rows.append(
            {
                "security_code": code,
                "security_name": item.get("security_name") or code,
                "sector": item.get("sector") or "未分類",
                "weight_pct": weight * 100.0,
                "avg_daily_volume": avg_volume,
                "position_quantity": quantity,
                "crowding_ratio": crowding_ratio,
            }
        )

    hhi = sum(value * value for value in sector_weight.values()) * 10000 if sector_weight else 0.0

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
            ), bal AS (
                SELECT AVG(COALESCE(market_value_base, market_value, 0)) AS avg_balance
                FROM fsi.balance_stock
                WHERE port_id = :fund_id
                  AND evaluate_date BETWEEN :start AND :end
            )
            SELECT COALESCE(buy_amount, 0) AS buy_amount,
                   COALESCE(sell_amount, 0) AS sell_amount,
                   COALESCE(avg_balance, 0) AS avg_balance
            FROM trades, bal
            """
        ),
        {"fund_id": fund_id, "start": period_start, "end": period_end},
    )
    turn_row = dict(turnover_result.mappings().first() or {})
    avg_balance = _number(turn_row.get("avg_balance"))
    one_way = min(_number(turn_row.get("buy_amount")), _number(turn_row.get("sell_amount")))
    turnover_pct = one_way / avg_balance * 100.0 if avg_balance else None

    crowding_rows.sort(key=lambda row: _number(row.get("crowding_ratio"), -1), reverse=True)
    warnings = []
    if hhi > 1800:
        warnings.append("行業集中度偏高（HHI > 1800）")
    if turnover_pct is not None and turnover_pct > 120:
        warnings.append("股票換手率偏高，存在擁擠交易風險")
    top_crowding = crowding_rows[0].get("crowding_ratio") if crowding_rows else None
    if top_crowding is not None and top_crowding > 0.25:
        warnings.append("頭部持倉相對日均成交量偏高，可能存在踩踏風險")

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "style_exposure": {
            "momentum_exposure": momentum_exposure if coverage_weight else None,
            "low_volatility_exposure": low_vol_exposure if coverage_weight else None,
            "size_exposure": size_exposure if coverage_weight else None,
            "coverage_weight": coverage_weight * 100.0,
        },
        "sector_concentration": {
            "hhi": hhi,
            "weights": [
                {"sector": sector, "weight_pct": weight * 100.0}
                for sector, weight in sorted(sector_weight.items(), key=lambda item: item[1], reverse=True)
            ],
        },
        "trading_behavior": {
            "turnover_pct": turnover_pct,
            "crowding_top": crowding_rows[:20],
        },
        "warnings": warnings,
    }
