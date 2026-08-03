"""Portfolio overview calculations."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _nav_history, _number, _performance_periods


async def compute_portfolio_overview(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """組合概況：總體業績、資產配置、前十大個股和股票行業配置。"""
    portfolio_result = await db.execute(
        text(
            """
            SELECT p.port_id AS fund_id, p.port_name, p.port_type::text AS portfolio_type,
                   p.base_currency, p.inception_date,
                   n.evaluate_date AS data_date, n.net_asset, n.shares_outstanding,
                   n.unit_nav, n.acc_unit_nav, n.day_return
            FROM fsi.para_portfolio p
            LEFT JOIN LATERAL (
                SELECT evaluate_date, net_asset, shares_outstanding,
                       unit_nav, acc_unit_nav, day_return
                FROM fsi.balance_portfolio_nav
                WHERE port_id = p.port_id
                  AND evaluate_date <= :as_of_date
                  AND currency = p.base_currency
                ORDER BY evaluate_date DESC
                LIMIT 1
            ) n ON TRUE
            WHERE p.port_id = :fund_id
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    portfolio_row = portfolio_result.mappings().first()
    portfolio = dict(portfolio_row) if portfolio_row else {
        "fund_id": fund_id,
        "port_name": fund_id,
        "data_date": None,
    }

    history = await _nav_history(db, fund_id, as_of_date)

    asset_result = await db.execute(
        text(
            """
            SELECT asset_class::text AS asset_class,
                   SUM(COALESCE(market_value_base, market_value)) AS market_value_base,
                   SUM(COALESCE(weight_pct, 0)) AS weight_pct
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            GROUP BY asset_class
            ORDER BY weight_pct DESC
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    asset_allocation = [dict(row) for row in asset_result.mappings().all()]

    stock_result = await db.execute(
        text(
            """
            SELECT security_code, security_name, market_id,
                   COALESCE(sector, '未分類') AS sector,
                   currency,
                   COALESCE(market_value_base, market_value) AS market_value_base,
                   COALESCE(weight_pct, 0) AS weight_pct,
                   unrealized_pnl
            FROM fsi.balance_stock
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            ORDER BY COALESCE(market_value_base, market_value) DESC
            LIMIT 10
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    top_stocks = [dict(row) for row in stock_result.mappings().all()]

    sector_result = await db.execute(
        text(
            """
            SELECT COALESCE(sector, '未分類') AS sector,
                   SUM(COALESCE(market_value_base, market_value)) AS market_value_base,
                   SUM(COALESCE(weight_pct, 0)) AS weight_pct,
                   COUNT(*) AS position_count
            FROM fsi.balance_stock
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            GROUP BY COALESCE(sector, '未分類')
            ORDER BY market_value_base DESC
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    stock_sectors = [dict(row) for row in sector_result.mappings().all()]

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "portfolio": portfolio,
        "performance": _performance_periods(history),
        "asset_allocation": asset_allocation,
        "top_stocks": top_stocks,
        "stock_sectors": stock_sectors,
    }
