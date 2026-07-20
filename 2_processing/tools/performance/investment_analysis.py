"""投資風險分析的確定性計算。

所有指標只依賴 FSI 業務表並在 Processing 層計算；Web/backend 僅做代理和展示。
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

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
                   MAX(net_asset) AS net_asset
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
