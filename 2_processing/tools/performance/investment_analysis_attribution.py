"""Performance attribution calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import (
    _benchmark_id,
    _date_value,
    _index_history,
    _nav_history,
    _number,
    _return_between,
)


def _security_period_returns(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["security_code"])].append(
            (_date_value(row["price_date"]), _number(row["close_price"]))
        )
    return {
        code: value
        for code, points in grouped.items()
        if (value := _return_between(sorted(points))) is not None
    }


async def _attribution_holdings(
    db: AsyncSession,
    fund_id: str,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    holdings_result = await db.execute(
        text(
            """
            SELECT security_code, MAX(security_name) AS security_name,
                   COALESCE(sector, '未分類') AS sector,
                   AVG(COALESCE(weight_pct, 0)) / 100.0 AS average_weight,
                   COUNT(DISTINCT evaluate_date) AS holding_days
            FROM fsi.balance_stock
            WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
            GROUP BY security_code, COALESCE(sector, '未分類')
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    holdings = [dict(row) for row in holdings_result.mappings().all()]
    quotes_result = await db.execute(
        text(
            """
            SELECT q.price_date, q.security_code, q.close_price
            FROM fsi.mktdata_quotes q
            WHERE q.price_type = 'CLOSE'
              AND q.price_date BETWEEN :start AND :end
              AND EXISTS (
                  SELECT 1 FROM fsi.balance_stock b
                  WHERE b.port_id = :fund_id
                    AND b.evaluate_date BETWEEN :start AND :end
                    AND b.security_code = q.security_code
              )
            ORDER BY q.security_code, q.price_date
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    return holdings, [dict(row) for row in quotes_result.mappings().all()]


async def _benchmark_sector_data(
    db: AsyncSession,
    benchmark_id: str | None,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not benchmark_id:
        return [], []
    component_result = await db.execute(
        text(
            """
            WITH latest_rebalance AS (
                SELECT MAX(rebal_date) AS value
                FROM fsi.mktdata_index_component
                WHERE index_code = :benchmark_id AND rebal_date <= :end
            )
            SELECT c.security_code,
                   COALESCE(s.security_name, c.security_code) AS security_name,
                   COALESCE(s.sector_level1, '未分類') AS sector,
                   COALESCE(c.weight_pct, 0) / 100.0 AS average_weight
            FROM fsi.mktdata_index_component c
            LEFT JOIN fsi.mktdata_stock_static s ON s.security_code = c.security_code
            WHERE c.index_code = :benchmark_id
              AND c.rebal_date = (SELECT value FROM latest_rebalance)
            """
        ),
        {"benchmark_id": benchmark_id, "end": end},
    )
    components = [dict(row) for row in component_result.mappings().all()]
    quote_result = await db.execute(
        text(
            """
            WITH latest_rebalance AS (
                SELECT MAX(rebal_date) AS value
                FROM fsi.mktdata_index_component
                WHERE index_code = :benchmark_id AND rebal_date <= :end
            )
            SELECT q.price_date, q.security_code, q.close_price
            FROM fsi.mktdata_quotes q
            JOIN fsi.mktdata_index_component c ON c.security_code = q.security_code
            WHERE c.index_code = :benchmark_id
              AND c.rebal_date = (SELECT value FROM latest_rebalance)
              AND q.price_type = 'CLOSE'
              AND q.price_date BETWEEN :start AND :end
            ORDER BY q.security_code, q.price_date
            """
        ),
        {"benchmark_id": benchmark_id, "start": start, "end": end},
    )
    return components, [dict(row) for row in quote_result.mappings().all()]


def _sector_weights_and_returns(
    holdings: list[dict[str, Any]],
    returns: dict[str, float],
) -> dict[str, tuple[float, float]]:
    total_weight = sum(_number(row.get("average_weight")) for row in holdings)
    sector_weight: dict[str, float] = defaultdict(float)
    sector_weighted_return: dict[str, float] = defaultdict(float)
    for row in holdings:
        sector = str(row.get("sector") or "未分類")
        raw_weight = _number(row.get("average_weight"))
        weight = raw_weight / total_weight if total_weight else 0.0
        security_return = returns.get(str(row["security_code"]), 0.0)
        sector_weight[sector] += weight
        sector_weighted_return[sector] += weight * security_return
    return {
        sector: (
            weight,
            sector_weighted_return[sector] / weight if weight else 0.0,
        )
        for sector, weight in sector_weight.items()
    }


async def compute_performance_attribution(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """收益貢獻、行業 Brinson 歸因、超配及個股損益排名。"""
    history = await _nav_history(db, fund_id, period_end, period_start)
    nav_points = [(_date_value(row["evaluate_date"]), _number(row["nav"])) for row in history]
    fund_return = _return_between(nav_points) or 0.0
    start_net_asset = _number(history[0].get("net_asset")) if history else 0.0

    benchmark_id = await _benchmark_id(db, fund_id, period_end)
    benchmark_points = await _index_history(db, benchmark_id, period_start, period_end) if benchmark_id else []
    benchmark_return = _return_between(benchmark_points) or 0.0

    fund_holdings, fund_quotes = await _attribution_holdings(db, fund_id, period_start, period_end)
    benchmark_holdings, benchmark_quotes = await _benchmark_sector_data(
        db, benchmark_id, period_start, period_end
    )
    fund_sectors = _sector_weights_and_returns(
        fund_holdings, _security_period_returns(fund_quotes)
    )
    benchmark_sectors = _sector_weights_and_returns(
        benchmark_holdings, _security_period_returns(benchmark_quotes)
    )

    allocation = 0.0
    selection = 0.0
    interaction = 0.0
    sector_attribution: list[dict[str, Any]] = []
    for sector in sorted(set(fund_sectors) | set(benchmark_sectors)):
        fund_weight, sector_fund_return = fund_sectors.get(sector, (0.0, 0.0))
        benchmark_weight, sector_benchmark_return = benchmark_sectors.get(sector, (0.0, 0.0))
        allocation_effect = (fund_weight - benchmark_weight) * (
            sector_benchmark_return - benchmark_return
        )
        selection_effect = benchmark_weight * (sector_fund_return - sector_benchmark_return)
        interaction_effect = (fund_weight - benchmark_weight) * (
            sector_fund_return - sector_benchmark_return
        )
        allocation += allocation_effect
        selection += selection_effect
        interaction += interaction_effect
        sector_attribution.append(
            {
                "sector": sector,
                "fund_weight_pct": fund_weight * 100.0,
                "benchmark_weight_pct": benchmark_weight * 100.0,
                "overweight_pct": (fund_weight - benchmark_weight) * 100.0,
                "fund_return_pct": sector_fund_return * 100.0,
                "benchmark_return_pct": sector_benchmark_return * 100.0,
                "allocation_effect_pct": allocation_effect * 100.0,
                "selection_effect_pct": selection_effect * 100.0,
                "interaction_effect_pct": interaction_effect * 100.0,
            }
        )
    sector_attribution.sort(key=lambda row: abs(row["overweight_pct"]), reverse=True)

    contribution_result = await db.execute(
        text(
            """
            SELECT COALESCE(asset_class::text, 'OTHER') AS asset_class,
                   SUM(COALESCE(mtm_delta, 0)) AS mtm_delta,
                   SUM(COALESCE(interest_income, 0)) AS interest_income,
                   SUM(COALESCE(realized_gain, 0)) AS realized_gain,
                   SUM(COALESCE(fx_pnl, 0)) AS fx_pnl,
                   SUM(COALESCE(fee_expense, 0)) AS fee_expense,
                   SUM(COALESCE(net_pnl_base, net_pnl, 0)) AS net_pnl
            FROM fsi.transact_pnl_item
            WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
            GROUP BY COALESCE(asset_class::text, 'OTHER')
            ORDER BY net_pnl DESC
            """
        ),
        {"fund_id": fund_id, "start": period_start, "end": period_end},
    )
    asset_contribution = []
    for row in contribution_result.mappings().all():
        item = dict(row)
        item["contribution_pct"] = (
            _number(item.get("net_pnl")) / start_net_asset * 100.0 if start_net_asset else None
        )
        asset_contribution.append(item)

    pnl_result = await db.execute(
        text(
            """
            SELECT p.security_code,
                   COALESCE(MAX(s.security_name), p.security_code, '未分類') AS security_name,
                   COALESCE(MAX(s.sector_level1), '未分類') AS sector,
                   SUM(COALESCE(p.net_pnl_base, p.net_pnl, 0)) AS net_pnl
            FROM fsi.transact_pnl_item p
            LEFT JOIN fsi.mktdata_stock_static s ON s.security_code = p.security_code
            WHERE p.port_id = :fund_id
              AND p.evaluate_date BETWEEN :start AND :end
              AND p.asset_class::text = 'STOCK'
            GROUP BY p.security_code
            """
        ),
        {"fund_id": fund_id, "start": period_start, "end": period_end},
    )
    pnl_rows = [dict(row) for row in pnl_result.mappings().all()]
    for row in pnl_rows:
        row["contribution_pct"] = (
            _number(row.get("net_pnl")) / start_net_asset * 100.0 if start_net_asset else None
        )
    top_winners = sorted(pnl_rows, key=lambda row: _number(row.get("net_pnl")), reverse=True)[:10]
    top_losers = sorted(pnl_rows, key=lambda row: _number(row.get("net_pnl")))[:10]

    pnl_by_security = {str(row.get("security_code")): row for row in pnl_rows}
    average_holdings = sorted(
        [
            {
                "security_code": row["security_code"],
                "security_name": row.get("security_name") or row["security_code"],
                "sector": row.get("sector") or "未分類",
                "average_weight_pct": _number(row.get("average_weight")) * 100.0,
                "holding_days": int(row.get("holding_days") or 0),
                "net_pnl": _number(pnl_by_security.get(str(row["security_code"]), {}).get("net_pnl")),
            }
            for row in fund_holdings
        ],
        key=lambda row: row["average_weight_pct"],
        reverse=True,
    )[:10]

    return {
        "fund_id": fund_id,
        "period_start": period_start,
        "period_end": period_end,
        "benchmark_id": benchmark_id,
        "summary": {
            "fund_return_pct": fund_return * 100.0,
            "benchmark_return_pct": benchmark_return * 100.0,
            "active_return_pct": (fund_return - benchmark_return) * 100.0,
            "allocation_effect_pct": allocation * 100.0,
            "selection_effect_pct": selection * 100.0,
            "interaction_effect_pct": interaction * 100.0,
        },
        "asset_contribution": asset_contribution,
        "sector_attribution": sector_attribution,
        "top_winners": top_winners,
        "top_losers": top_losers,
        "average_top_holdings": average_holdings,
    }
