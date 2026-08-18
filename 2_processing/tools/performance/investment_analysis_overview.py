"""Portfolio overview calculations."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _nav_history, _number, _performance_periods


async def _latest_snapshot_date(
    db: AsyncSession,
    table: str,
    fund_id: str,
    as_of_date: date,
) -> date | None:
    """Latest evaluate_date on/before as_of_date for a balance table.

    Holdings snapshots are not loaded every calendar day, so an exact-date match
    silently returns nothing. Resolving the latest available date mirrors the risk
    dashboard's fallback behaviour and keeps overview holdings in sync with it.
    """
    result = await db.execute(
        text(
            f"""
            SELECT MAX(evaluate_date) AS value
            FROM fsi.{table}
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    return result.scalar_one_or_none()


async def compute_portfolio_overview(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """組合概況：總體業績、資產配置、前十大個股/個券和股票行業配置。"""
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

    asset_date = await _latest_snapshot_date(db, "balance_portfolio_asset", fund_id, as_of_date)
    stock_date = await _latest_snapshot_date(db, "balance_stock", fund_id, as_of_date)
    bond_date = await _latest_snapshot_date(db, "balance_bond", fund_id, as_of_date)

    asset_allocation: list[dict[str, Any]] = []
    if asset_date is not None:
        asset_result = await db.execute(
            text(
                """
                SELECT asset_class::text AS asset_class,
                       SUM(COALESCE(market_value_base, market_value)) AS market_value_base,
                       SUM(COALESCE(weight_pct, 0)) AS weight_pct
                FROM fsi.balance_portfolio_asset
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                GROUP BY asset_class
                ORDER BY weight_pct DESC
                """
            ),
            {"fund_id": fund_id, "snapshot": asset_date},
        )
        asset_allocation = [dict(row) for row in asset_result.mappings().all()]

    top_stocks: list[dict[str, Any]] = []
    stock_sectors: list[dict[str, Any]] = []
    if stock_date is not None:
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
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, market_value) DESC
                LIMIT 10
                """
            ),
            {"fund_id": fund_id, "snapshot": stock_date},
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
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                GROUP BY COALESCE(sector, '未分類')
                ORDER BY market_value_base DESC
                """
            ),
            {"fund_id": fund_id, "snapshot": stock_date},
        )
        stock_sectors = [dict(row) for row in sector_result.mappings().all()]

    top_bonds: list[dict[str, Any]] = []
    if bond_date is not None:
        bond_result = await db.execute(
            text(
                """
                SELECT security_code, security_name, market_id,
                       COALESCE(issuer_name, '—') AS issuer_name,
                       COALESCE(sector, '未分類') AS sector,
                       currency,
                       COALESCE(market_value_base, total_market_value, market_value) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       accrued_interest,
                       ytm, duration, coupon_rate,
                       maturity_date, remaining_days,
                       COALESCE(debt_rating, issuer_rating, internal_rating) AS rating
                FROM fsi.balance_bond
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, total_market_value, market_value) DESC
                LIMIT 10
                """
            ),
            {"fund_id": fund_id, "snapshot": bond_date},
        )
        top_bonds = [dict(row) for row in bond_result.mappings().all()]

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "snapshot_dates": {
            "asset": asset_date,
            "stock": stock_date,
            "bond": bond_date,
        },
        "portfolio": portfolio,
        "performance": _performance_periods(history),
        "asset_allocation": asset_allocation,
        "top_stocks": top_stocks,
        "top_bonds": top_bonds,
        "stock_sectors": stock_sectors,
    }
