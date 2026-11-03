"""用独立 Brinson / Campisi 模型计算业绩归因，供页面切换展示。"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _date_value, _number
from .models.brinson import brinson
from .models.campisi import campisi, interpolate_yield

logger = logging.getLogger(__name__)

_MAX_PERIODS = 24

# Campisi 国债效应：按持仓币种选择政府债曲线
_CURRENCY_CURVE = {
    "USD": "US_TREAS",
    "CNY": "CN_TREAS",
    "CNH": "CN_TREAS",
    "HKD": "HKGOV",
}
_CURVE_FALLBACK = ("US_TREAS", "CN_TREAS", "HKGOV")


async def list_attribution_benchmarks(
    db: AsyncSession,
    fund_id: str,
    as_of: date,
) -> dict[str, Any]:
    """组合已配置基准 + 基准定义 + mktdata_index 指数目录，供归因/因子风险页选择。"""
    result = await db.execute(
        text(
            """
            WITH catalog AS (
              SELECT d.benchmark_id,
                     d.benchmark_name,
                     d.benchmark_type,
                     d.source,
                     d.source_ticker
              FROM fsi.para_benchmark_def d
              WHERE d.is_active
              UNION ALL
              SELECT i.index_code AS benchmark_id,
                     COALESCE(i.index_name, i.index_code) AS benchmark_name,
                     'INDEX' AS benchmark_type,
                     'mktdata_index' AS source,
                     i.index_code AS source_ticker
              FROM fsi.mktdata_index i
              WHERE NOT EXISTS (
                SELECT 1 FROM fsi.para_benchmark_def d
                WHERE d.benchmark_id = i.index_code AND d.is_active
              )
            )
            SELECT c.benchmark_id,
                   c.benchmark_name,
                   c.benchmark_type,
                   c.source,
                   c.source_ticker,
                   pb.benchmark_role,
                   pb.weight_pct,
                   (
                     SELECT COUNT(*) FROM fsi.mktdata_index_component ic
                     WHERE ic.index_code = c.benchmark_id
                   ) AS equity_components,
                   (
                     SELECT COUNT(*) FROM fsi.mktdata_index_quotes q
                     WHERE q.index_code = c.benchmark_id
                   ) AS quote_count,
                   0 AS bond_components
            FROM catalog c
            LEFT JOIN fsi.para_portfolio_benchmark pb
              ON pb.benchmark_id = c.benchmark_id
             AND pb.port_id = :fund_id
             AND pb.begin_date <= :as_of
             AND (pb.end_date IS NULL OR pb.end_date >= :as_of)
            ORDER BY (pb.port_id IS NOT NULL) DESC,
                     (pb.benchmark_role = 'PRIMARY') DESC,
                     c.benchmark_id
            """
        ),
        {"fund_id": fund_id, "as_of": as_of},
    )
    items = []
    for row in result.mappings().all():
        items.append(
            {
                "benchmark_id": row["benchmark_id"],
                "benchmark_name": row["benchmark_name"],
                "benchmark_type": row["benchmark_type"],
                "source": row["source"],
                "source_ticker": row["source_ticker"],
                "assigned": row["benchmark_role"] is not None,
                "benchmark_role": row["benchmark_role"],
                "weight_pct": float(row["weight_pct"]) if row["weight_pct"] is not None else None,
                "equity_components": int(row["equity_components"] or 0),
                "bond_components": int(row["bond_components"] or 0),
                "quote_count": int(row["quote_count"] or 0),
            }
        )
    return {"fund_id": fund_id, "as_of_date": as_of, "benchmarks": items}


async def compute_model_attribution(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
    benchmark_id: str | None,
) -> dict[str, Any]:
    """请求内实时计算 Brinson / Campisi / 收益贡献，不读报表层。"""
    import time

    from .investment_analysis_contribution import compute_contribution_model

    started = time.perf_counter()
    try:
        frames = await _load_frames(db, fund_id, period_start, period_end, benchmark_id)
        contribution_model = await compute_contribution_model(db, fund_id, period_start, period_end)
        payload = {
            "source": "realtime",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "brinson_model": _brinson_views(frames),
            "campisi_model": _campisi_views(frames),
            "contribution_model": contribution_model,
        }
        return payload
    except Exception:
        logger.exception("model attribution failed for %s", fund_id)
        return {
            "source": "realtime",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "brinson_model": {"error": "brinson_unavailable", "views": {}},
            "campisi_model": {"error": "campisi_unavailable", "views": {}},
            "contribution_model": {"error": "contribution_unavailable", "views": {}},
        }


async def _load_frames(
    db: AsyncSession,
    fund_id: str,
    start: date,
    end: date,
    benchmark_id: str | None,
) -> dict[str, Any]:
    stocks = await _rows(
        db,
        """
        SELECT evaluate_date AS as_of, security_code, MAX(security_name) AS security_name,
               COALESCE(NULLIF(sector, ''), '未分类') AS industry,
               SUM(COALESCE(weight_pct, 0)) / 100.0 AS weight
        FROM fsi.balance_stock
        WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
        GROUP BY evaluate_date, security_code, COALESCE(NULLIF(sector, ''), '未分类')
        """,
        {"fund_id": fund_id, "start": start, "end": end},
    )
    bonds = await _rows(
        db,
        """
        SELECT evaluate_date AS as_of, security_code, MAX(security_name) AS security_name,
               COALESCE(NULLIF(issuer_name, ''), '债券') AS industry,
               MAX(COALESCE(NULLIF(currency, ''), 'USD')) AS currency,
               SUM(COALESCE(weight_pct, 0)) / 100.0 AS weight,
               AVG(COALESCE(duration, 0)) AS duration,
               AVG(COALESCE(convexity, 0)) AS convexity,
               AVG(coupon_rate) AS coupon_rate,
               AVG(clean_price) AS clean_price,
               AVG(ytm) AS ytm,
               MAX(maturity_date) AS maturity_date
        FROM fsi.balance_bond
        WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
        GROUP BY evaluate_date, security_code, COALESCE(NULLIF(issuer_name, ''), '债券')
        """,
        {"fund_id": fund_id, "start": start, "end": end},
    )
    for row in stocks:
        row["asset"] = "股票"
    for row in bonds:
        row["asset"] = "债券"
    bench_rows = await _benchmark_constituents(db, benchmark_id, start, end) if benchmark_id else []
    codes = sorted({str(row["security_code"]) for row in stocks + bonds + bench_rows})
    quotes = await _quote_map(db, codes, start, end)
    curve = await _treasury_curve(db, start, end)
    dates = _sample_dates(sorted({_date_value(row["as_of"]) for row in stocks + bonds}))
    portfolio_periods, campisi_periods = _portfolio_periods(stocks, bonds, quotes, curve, dates, start, end)
    benchmark_periods = _benchmark_periods(bench_rows, quotes, dates, start, end, portfolio_periods)
    return {
        "benchmark_id": benchmark_id,
        "benchmark_source": "index_component" if bench_rows else "asset_proxy",
        "portfolio_periods": portfolio_periods,
        "benchmark_periods": benchmark_periods,
        "campisi_periods": campisi_periods,
        "period_count": len(portfolio_periods),
    }


async def _rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await db.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def _quote_map(db: AsyncSession, codes: list[str], start: date, end: date) -> dict[str, list[tuple[date, float]]]:
    if not codes:
        return {}
    result = await db.execute(
        text(
            """
            SELECT security_code, price_date, close_price
            FROM fsi.mktdata_quotes
            WHERE price_type = 'CLOSE'
              AND price_date BETWEEN :start AND :end
              AND security_code IN :codes
            ORDER BY security_code, price_date
            """
        ).bindparams(bindparam("codes", expanding=True)),
        {"start": start, "end": end, "codes": codes},
    )
    grouped: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in result.mappings().all():
        price = _number(row["close_price"])
        if price:
            grouped[str(row["security_code"])].append((_date_value(row["price_date"]), price))
    return grouped


async def _benchmark_constituents(
    db: AsyncSession,
    benchmark_id: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """区间内每个调仓日的成分。归因按持仓日前最近一个调仓日取权重。"""
    equity = await db.execute(
        text(
            """
            SELECT c.rebal_date,
                   c.security_code,
                   CASE WHEN upper(COALESCE(i.asset_class, '')) = 'BOND' THEN '债券'
                        ELSE COALESCE(ind.level1_name, ind.industry_name, '未分类') END AS industry,
                   COALESCE(c.weight_pct, 0) / 100.0 AS weight,
                   CASE WHEN upper(COALESCE(i.asset_class, '')) = 'BOND' THEN '债券'
                        ELSE '股票' END AS asset
            FROM fsi.mktdata_index_component c
            LEFT JOIN fsi.mktdata_index i ON i.index_code = c.index_code
            LEFT JOIN fsi.mktdata_stock_static s ON s.security_code = c.security_code
            LEFT JOIN LATERAL (
                SELECT x.industry_name, x.level1_name
                FROM fsi.v_mktdata_stock_industry_current x
                WHERE x.security_code = c.security_code
                ORDER BY (x.standard = 'GICS') DESC, x.is_primary DESC
                LIMIT 1
            ) ind ON TRUE
            WHERE c.index_code = :benchmark_id
              AND c.rebal_date BETWEEN :start AND :end
            """
        ),
        {"benchmark_id": benchmark_id, "start": start, "end": end},
    )
    rows = []
    for row in equity.mappings().all():
        item = dict(row)
        item["rebal_date"] = _date_value(item["rebal_date"])
        rows.append(item)
    if rows:
        return rows
    # 区间内没有成分时，用结束日之前最近一次调仓
    return await _benchmark_constituents_latest(db, benchmark_id, end)


async def _benchmark_constituents_latest(db: AsyncSession, benchmark_id: str, end: date) -> list[dict[str, Any]]:
    equity = await db.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(rebal_date) AS value
                FROM fsi.mktdata_index_component
                WHERE index_code = :benchmark_id AND rebal_date <= :end
            )
            SELECT c.rebal_date, c.security_code,
                   CASE WHEN upper(COALESCE(i.asset_class, '')) = 'BOND' THEN '债券'
                        ELSE COALESCE(ind.level1_name, ind.industry_name, '未分类') END AS industry,
                   COALESCE(c.weight_pct, 0) / 100.0 AS weight,
                   CASE WHEN upper(COALESCE(i.asset_class, '')) = 'BOND' THEN '债券'
                        ELSE '股票' END AS asset
            FROM fsi.mktdata_index_component c
            LEFT JOIN fsi.mktdata_index i ON i.index_code = c.index_code
            LEFT JOIN fsi.mktdata_stock_static s ON s.security_code = c.security_code
            LEFT JOIN LATERAL (
                SELECT x.industry_name, x.level1_name
                FROM fsi.v_mktdata_stock_industry_current x
                WHERE x.security_code = c.security_code
                ORDER BY (x.standard = 'GICS') DESC, x.is_primary DESC
                LIMIT 1
            ) ind ON TRUE
            WHERE c.index_code = :benchmark_id
              AND c.rebal_date = (SELECT value FROM latest)
            """
        ),
        {"benchmark_id": benchmark_id, "end": end},
    )
    rows = []
    for row in equity.mappings().all():
        item = dict(row)
        item["rebal_date"] = _date_value(item["rebal_date"])
        rows.append(item)
    return rows


async def _treasury_curve(
    db: AsyncSession, start: date, end: date
) -> dict[str, dict[date, list[tuple[float, float]]]]:
    """按曲线 ID 返回政府债收益率曲线；向前多取一段便于期初插值。"""
    from datetime import timedelta

    lookback = start - timedelta(days=45)
    result = await db.execute(
        text(
            """
            SELECT curve_id, rate_date, tenor_days, rate
            FROM fsi.mktdata_yield_curve_quotes
            WHERE curve_id IN ('US_TREAS', 'CN_TREAS', 'HKGOV')
              AND rate_date BETWEEN :lookback AND :end
              AND tenor_days IS NOT NULL
            ORDER BY curve_id, rate_date, tenor_days
            """
        ),
        {"lookback": lookback, "end": end},
    )
    curves: dict[str, dict[date, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    for row in result.mappings().all():
        rate = _number(row["rate"])
        # 兼容误存百分数的历史行
        if abs(rate) > 1.5:
            rate /= 100.0
        curves[str(row["curve_id"])][_date_value(row["rate_date"])].append(
            (float(row["tenor_days"]) / 365.0, rate)
        )
    return {curve_id: dict(points) for curve_id, points in curves.items()}


def _curve_for_currency(
    curves: dict[str, dict[date, list[tuple[float, float]]]],
    currency: str | None,
) -> dict[date, list[tuple[float, float]]]:
    preferred = _CURRENCY_CURVE.get(str(currency or "").upper(), "US_TREAS")
    if preferred in curves and curves[preferred]:
        return curves[preferred]
    for curve_id in _CURVE_FALLBACK:
        if curve_id in curves and curves[curve_id]:
            return curves[curve_id]
    return {}


def _sample_dates(dates: list[date]) -> list[date]:
    if len(dates) <= _MAX_PERIODS + 1:
        return dates
    step = max(1, len(dates) // _MAX_PERIODS)
    sampled = dates[::step]
    if sampled[-1] != dates[-1]:
        sampled.append(dates[-1])
    return sampled


def _price_on_or_before(series: list[tuple[date, float]], day: date) -> float | None:
    chosen = None
    for point_day, price in series:
        if point_day <= day:
            chosen = price
        else:
            break
    return chosen


def _period_return(series: list[tuple[date, float]], start: date, end: date) -> float:
    begin = _price_on_or_before(series, start)
    finish = _price_on_or_before(series, end)
    if not begin or finish is None:
        return 0.0
    return finish / begin - 1.0


def _rate(value: Any) -> float:
    number = _number(value)
    if abs(number) > 1.5:
        return number / 100.0
    return number


def _years_to_maturity(maturity: Any, day: date) -> float:
    if maturity is None:
        return 1.0
    try:
        remaining = (_date_value(maturity) - day).days / 365.0
    except Exception:
        return 1.0
    return max(remaining, 0.05)


def _treasury_change(
    curve: dict[date, list[tuple[float, float]]],
    start: date,
    end: date,
    tenor: float,
) -> float:
    begin_curve = _curve_on_or_before(curve, start)
    end_curve = _curve_on_or_before(curve, end)
    if not begin_curve or not end_curve:
        return 0.0
    begin = interpolate_yield(begin_curve, tenor)
    finish = interpolate_yield(end_curve, tenor)
    if begin is None or finish is None:
        return 0.0
    return finish - begin


def _curve_on_or_before(curve: dict[date, list[tuple[float, float]]], day: date) -> list[tuple[float, float]]:
    chosen: list[tuple[float, float]] = []
    for point_day in sorted(curve):
        if point_day <= day:
            chosen = curve[point_day]
        else:
            break
    return chosen


def _portfolio_periods(
    stocks: list[dict[str, Any]],
    bonds: list[dict[str, Any]],
    quotes: dict[str, list[tuple[date, float]]],
    curves: dict[str, dict[date, list[tuple[float, float]]]],
    dates: list[date],
    window_start: date,
    window_end: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    holdings_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in stocks + bonds:
        holdings_by_day[_date_value(row["as_of"])].append(row)
    if len(dates) < 2:
        day = dates[-1] if dates else window_end
        holdings = holdings_by_day.get(day) or holdings_by_day.get(dates[-1] if dates else day, [])
        port, camp = _slice(holdings, quotes, curves, window_start, window_end, day)
        return ([port] if port else []), ([camp] if camp else [])
    portfolio_periods = []
    campisi_periods = []
    for begin, finish in zip(dates, dates[1:]):
        port, camp = _slice(holdings_by_day.get(begin, []), quotes, curves, begin, finish, finish)
        if port:
            portfolio_periods.append(port)
        if camp:
            campisi_periods.append(camp)
    return portfolio_periods, campisi_periods


def _slice(
    holdings: list[dict[str, Any]],
    quotes: dict[str, list[tuple[date, float]]],
    curves: dict[str, dict[date, list[tuple[float, float]]]],
    begin: date,
    finish: date,
    label_day: date,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not holdings:
        return None, None
    port_rows = []
    camp_rows = []
    holding_days = max((finish - begin).days, 1)
    industry_spread: dict[str, list[tuple[float, float]]] = defaultdict(list)
    prepared = []
    for row in holdings:
        code = str(row["security_code"])
        weight = _number(row.get("weight"))
        asset = str(row.get("asset") or "其他")
        industry = str(row.get("industry") or "未分类")
        series = quotes.get(code, [])
        if asset == "债券":
            price_begin = _number(row.get("clean_price")) or _price_on_or_before(series, begin) or 100.0
            price_end = _price_on_or_before(series, finish) or price_begin
            coupon = _rate(row.get("coupon_rate"))
            income = coupon * holding_days / 365.0
            price_return = (price_end - price_begin) / price_begin if price_begin else 0.0
            total = income + price_return
            tenor = _years_to_maturity(row.get("maturity_date"), finish)
            duration_val = _number(row.get("duration")) or tenor_fallback(row, finish)
            curve = _curve_for_currency(curves, row.get("currency"))
            dy = _treasury_change(curve, begin, finish, tenor)
            # 无历史 YTM/OAS 时，用价格反推总收益率变化，再扣国债得到利差变化
            ytm_change = (-price_return / duration_val) if duration_val > 1e-8 else 0.0
            spread_change = ytm_change - dy
            prepared.append((row, weight, asset, industry, total, income, dy, spread_change, duration_val))
            industry_spread[industry].append((weight, spread_change))
        else:
            total = _period_return(series, begin, finish)
            prepared.append((row, weight, asset, industry, total, 0.0, 0.0, 0.0, 0.0))
    industry_avg = {
        name: (sum(w * v for w, v in pairs) / sum(w for w, _ in pairs) if sum(w for w, _ in pairs) else 0.0)
        for name, pairs in industry_spread.items()
    }
    # 行业只有 1 只券时行业均值=自身，择券会被吃掉；退回组合加权利差作为共同因子
    all_spread_pairs = [pair for pairs in industry_spread.values() for pair in pairs]
    portfolio_spread = (
        sum(w * v for w, v in all_spread_pairs) / sum(w for w, _ in all_spread_pairs)
        if all_spread_pairs and sum(w for w, _ in all_spread_pairs)
        else 0.0
    )
    for row, weight, asset, industry, total, income, dy, spread_change, duration_val in prepared:
        code = str(row["security_code"])
        port_rows.append(
            {
                "date": label_day,
                "symbol": code,
                "weight": weight,
                "asset": asset,
                "industry": industry,
                "return_period": total,
            }
        )
        if asset == "债券":
            peers = industry_spread.get(industry) or []
            common_spread = industry_avg.get(industry, spread_change) if len(peers) >= 2 else portfolio_spread
            camp_rows.append(
                {
                    "date": label_day,
                    "symbol": code,
                    "weight": weight,
                    "asset": asset,
                    "industry": industry,
                    "total_return": total,
                    "income": income,
                    "duration": duration_val or tenor_fallback(row, finish),
                    "convexity": _number(row.get("convexity")),
                    "treasury_change": dy,
                    # 有基准时：共同利差因子；个券相对残差进入择券
                    "spread_change": common_spread,
                }
            )
    return (
        {"date": label_day, "rows": port_rows} if port_rows else None,
        {"date": label_day, "rows": camp_rows} if camp_rows else None,
    )


def tenor_fallback(row: dict[str, Any], day: date) -> float:
    return max(_years_to_maturity(row.get("maturity_date"), day), 0.25)


def _constituents_as_of(constituents: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    dated = [row for row in constituents if row.get("rebal_date") is not None and row["rebal_date"] <= day]
    if not dated:
        return [row for row in constituents if row.get("rebal_date") is None]
    latest = max(row["rebal_date"] for row in dated)
    return [row for row in dated if row["rebal_date"] == latest]


def _benchmark_periods(
    constituents: list[dict[str, Any]],
    quotes: dict[str, list[tuple[date, float]]],
    dates: list[date],
    window_start: date,
    window_end: date,
    portfolio_periods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not constituents:
        # 没有指数成分时，用组合自身的资产类别等权作为对照，避免页面空白
        periods = []
        for period in portfolio_periods:
            by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in period["rows"]:
                by_asset[row["asset"]].append(row)
            rows = []
            share = 1.0 / len(by_asset) if by_asset else 0.0
            for asset, members in by_asset.items():
                ret = sum(item["weight"] * item["return_period"] for item in members)
                weight_sum = sum(item["weight"] for item in members) or 1.0
                rows.append(
                    {
                        "date": period["date"],
                        "symbol": f"BENCH-{asset}",
                        "weight": share,
                        "asset": asset,
                        "industry": members[0]["industry"],
                        "return_period": ret / weight_sum,
                    }
                )
            periods.append({"date": period["date"], "rows": rows})
        return periods
    windows = [(window_start, window_end, dates[-1] if dates else window_end)] if len(dates) < 2 else list(zip(dates, dates[1:], dates[1:]))
    periods = []
    for begin, finish, label in windows:
        rows = []
        for item in _constituents_as_of(constituents, begin):
            code = str(item["security_code"])
            rows.append(
                {
                    "date": label,
                    "symbol": code,
                    "weight": _number(item.get("weight")),
                    "asset": "股票",
                    "industry": str(item.get("industry") or "未分类"),
                    "return_period": _period_return(quotes.get(code, []), begin, finish),
                }
            )
        periods.append({"date": label, "rows": rows})
    return periods


def _flatten(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for period in periods for row in period["rows"]]


def _single_book(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把多期压成一期：权重取平均，收益复利。"""
    if not periods:
        return []
    bucket: dict[str, dict[str, Any]] = {}
    for period in periods:
        seen = set()
        for row in period["rows"]:
            key = str(row["symbol"])
            seen.add(key)
            item = bucket.setdefault(
                key,
                {
                    "symbol": key,
                    "weight": 0.0,
                    "growth": 1.0,
                    "asset": row.get("asset"),
                    "industry": row.get("industry"),
                    "n": 0,
                    "income": 0.0,
                    "duration": 0.0,
                    "convexity": 0.0,
                    "treasury_change": 0.0,
                    "spread_change": 0.0,
                    "present": 0,
                },
            )
            item["weight"] += float(row.get("weight") or 0.0)
            item["n"] += 1
            item["growth"] *= 1.0 + float(row.get("return_period") or row.get("total_return") or 0.0)
            if "income" in row:
                item["income"] += float(row.get("income") or 0.0)
                item["duration"] += float(row.get("duration") or 0.0)
                item["convexity"] += float(row.get("convexity") or 0.0)
                item["treasury_change"] += float(row.get("treasury_change") or 0.0)
                item["spread_change"] += float(row.get("spread_change") or 0.0)
                item["present"] += 1
        for key, item in bucket.items():
            if key not in seen:
                item["growth"] *= 1.0
    day = periods[-1]["date"]
    rows = []
    for item in bucket.values():
        n = item["n"] or 1
        base = {
            "date": day,
            "symbol": item["symbol"],
            "weight": item["weight"] / n,
            "asset": item["asset"],
            "industry": item["industry"],
            "return_period": item["growth"] - 1.0,
        }
        if item["present"]:
            p = item["present"]
            base.update(
                {
                    "total_return": item["growth"] - 1.0,
                    "income": item["income"],
                    "duration": item["duration"] / p,
                    "convexity": item["convexity"] / p,
                    "treasury_change": item["treasury_change"],
                    "spread_change": item["spread_change"],
                }
            )
        rows.append(base)
    return rows


def _brinson_views(frames: dict[str, Any]) -> dict[str, Any]:
    multi_port = _flatten(frames["portfolio_periods"])
    multi_bench = _flatten(frames["benchmark_periods"])
    single_port = _single_book(frames["portfolio_periods"])
    single_bench = _single_book(frames["benchmark_periods"])
    views = {}
    for method in ("BHB", "BF"):
        for mode, port, bench, multi in (
            ("single", single_port, single_bench, False),
            ("grap", multi_port, multi_bench, True),
        ):
            for group_by in ("asset", "industry", "symbol", "portfolio"):
                raw = brinson(
                    port,
                    bench,
                    method=method,
                    multi_period=multi,
                    multi_period_method="grap",
                    group_by=group_by,
                    industry_within_assets=["股票"] if group_by == "asset" and method == "BHB" and multi else None,
                )
                views[f"{method}|{mode}|{group_by}"] = _present_brinson(raw)
    return {
        "benchmark_id": frames.get("benchmark_id"),
        "benchmark_source": frames.get("benchmark_source"),
        "period_count": frames.get("period_count") or 0,
        "views": views,
    }


def _campisi_views(frames: dict[str, Any]) -> dict[str, Any]:
    multi_rows = _flatten(frames["campisi_periods"])
    single_rows = [row for row in _single_book(frames["campisi_periods"]) if "total_return" in row]
    views = {}
    for benchmark in (False, True):
        for mode, rows, multi in (("single", single_rows, False), ("multi", multi_rows, True)):
            for group_by in ("industry", "symbol", "portfolio", "asset"):
                raw = campisi(
                    rows,
                    benchmark=benchmark,
                    convexity=False,
                    multi_period=multi,
                    group_by=group_by,
                )
                views[f"{'bench' if benchmark else 'absolute'}|{mode}|{group_by}"] = _present_campisi(raw)
    return {"period_count": len(frames.get("campisi_periods") or []), "views": views}


def _present_brinson(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": raw["method"],
        "multi_period": raw["multi_period"],
        "multi_period_method": raw["multi_period_method"],
        "group_by": raw["group_by"],
        "portfolio_return_pct": _pct(raw["portfolio_return"]),
        "benchmark_return_pct": _pct(raw["benchmark_return"]),
        "active_return_pct": _pct(raw["active_return"]),
        "allocation_effect_pct": _pct(raw["allocation"]),
        "selection_effect_pct": _pct(raw["selection"]),
        "interaction_effect_pct": _pct(raw["interaction"]),
        "groups": [
            {
                "group": row["group"],
                "portfolio_weight_pct": _pct(row["portfolio_weight"]),
                "benchmark_weight_pct": _pct(row["benchmark_weight"]),
                "portfolio_return_pct": _pct(row["portfolio_return"]),
                "benchmark_return_pct": _pct(row["benchmark_return"]),
                "allocation_effect_pct": _pct(row["allocation"]),
                "selection_effect_pct": _pct(row["selection"]),
                "interaction_effect_pct": _pct(row["interaction"]),
                "active_return_pct": _pct(row["active"]),
            }
            for row in raw["groups"]
        ],
    }


def _present_campisi(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark": raw["benchmark"],
        "multi_period": raw["multi_period"],
        "group_by": raw["group_by"],
        "total_return_pct": _pct(raw["total_return"]),
        "income_effect_pct": _pct(raw["income"]),
        "treasury_effect_pct": _pct(raw["treasury"]),
        "spread_effect_pct": _pct(raw["spread"]),
        "selection_effect_pct": _pct(raw["selection"]),
        "groups": [
            {
                "group": row["group"],
                "weight_pct": _pct(row["weight"]),
                "total_return_pct": _pct(row["total_return"]),
                "income_effect_pct": _pct(row["income"]),
                "treasury_effect_pct": _pct(row["treasury"]),
                "spread_effect_pct": _pct(row["spread"]),
                "selection_effect_pct": _pct(row["selection"]),
            }
            for row in raw["groups"]
        ],
    }


def _pct(value: float) -> float:
    return float(value) * 100.0
