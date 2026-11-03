"""个券收益贡献：从持仓 / 行情 / 损益 / 净值表取数，调用纯公式模块。"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _date_value, _number, _return_between
from .models.contribution import contribution

logger = logging.getLogger(__name__)


async def compute_contribution_model(
    db: AsyncSession,
    fund_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """实时计算收益贡献视图（单期 / 平均权重 / 日链 Carino）。"""
    holdings = await _load_holdings(db, fund_id, start, end)
    codes = sorted({str(row["security_code"]) for row in holdings})
    quotes = await _load_quotes(db, codes, start, end)
    nav_points = await _load_nav(db, fund_id, start, end)
    pnl_rows = await _load_pnl(db, fund_id, start, end)
    begin_nav = nav_points[0][1] if nav_points else 0.0
    portfolio_return = _return_between(nav_points) if len(nav_points) >= 2 else None

    single_rows = _static_period_rows(holdings, quotes, start, end)
    daily_rows = _daily_rows(holdings, quotes, start, end)
    average_rows = daily_rows if daily_rows else single_rows
    pnl_contrib_rows = _pnl_rows(holdings, pnl_rows, begin_nav, end)

    views: dict[str, Any] = {}
    for group_by in ("symbol", "asset", "industry", "portfolio"):
        views[f"single|{group_by}"] = _present(
            contribution(single_rows, mode="single", group_by=group_by, portfolio_return=portfolio_return)
        )
        views[f"average|{group_by}"] = _present(
            contribution(average_rows, mode="average", group_by=group_by, portfolio_return=portfolio_return)
        )
        views[f"daily|carino|{group_by}"] = _present(
            contribution(
                daily_rows or single_rows,
                mode="daily",
                link_method="carino",
                group_by=group_by,
                portfolio_return=portfolio_return,
            )
        )
        if pnl_contrib_rows:
            views[f"pnl|{group_by}"] = _present(
                contribution(pnl_contrib_rows, mode="single", group_by=group_by, portfolio_return=portfolio_return)
            )

    return {
        "period_count": len({row["date"] for row in daily_rows}) if daily_rows else (1 if single_rows else 0),
        "holding_count": len(codes),
        "has_pnl": bool(pnl_contrib_rows),
        "portfolio_return_pct": None if portfolio_return is None else portfolio_return * 100.0,
        "data_sources": {
            "holdings": "balance_stock+balance_bond",
            "quotes": "mktdata_quotes",
            "nav": "balance_portfolio_nav",
            "pnl": "transact_pnl_item" if pnl_contrib_rows else None,
            "valuation": "balance_valuation_sheet",
        },
        "views": views,
    }


def _present(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": raw["mode"],
        "link_method": raw["link_method"],
        "group_by": raw["group_by"],
        "portfolio_return_pct": _pct(raw["portfolio_return"]),
        "contribution_total_pct": _pct(raw["contribution_total"]),
        "residual_pct": _pct(raw["residual"]),
        "periods": raw.get("periods") or 1,
        "groups": [
            {
                "group": row["group"],
                "symbol": row.get("symbol"),
                "security_name": row.get("security_name"),
                "asset": row.get("asset"),
                "industry": row.get("industry"),
                "weight_pct": _pct(row["weight"]),
                "return_pct": _pct(row["return_period"]),
                "contribution_pct": _pct(row["contribution"]),
            }
            for row in raw["groups"]
        ],
    }


def _pct(value: float | None) -> float:
    return round(float(value or 0.0) * 100.0, 8)


async def _load_holdings(db: AsyncSession, fund_id: str, start: date, end: date) -> list[dict[str, Any]]:
    stock = await db.execute(
        text(
            """
            SELECT evaluate_date AS as_of, security_code,
                   MAX(security_name) AS security_name,
                   COALESCE(NULLIF(sector, ''), '未分类') AS industry,
                   '股票' AS asset,
                   SUM(COALESCE(weight_pct, 0)) / 100.0 AS weight,
                   SUM(COALESCE(market_value_base, market_value, 0)) AS market_value,
                   AVG(price) AS price
            FROM fsi.balance_stock
            WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
            GROUP BY evaluate_date, security_code, COALESCE(NULLIF(sector, ''), '未分类')
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    bond = await db.execute(
        text(
            """
            SELECT evaluate_date AS as_of, security_code,
                   MAX(security_name) AS security_name,
                   COALESCE(NULLIF(issuer_name, ''), COALESCE(NULLIF(sector, ''), '债券')) AS industry,
                   '债券' AS asset,
                   SUM(COALESCE(weight_pct, 0)) / 100.0 AS weight,
                   SUM(COALESCE(market_value_base, market_value, 0)) AS market_value,
                   AVG(COALESCE(clean_price, dirty_price)) AS price
            FROM fsi.balance_bond
            WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
            GROUP BY evaluate_date, security_code,
                     COALESCE(NULLIF(issuer_name, ''), COALESCE(NULLIF(sector, ''), '债券'))
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    rows = [dict(row) for row in stock.mappings().all()] + [dict(row) for row in bond.mappings().all()]
    for row in rows:
        row["as_of"] = _date_value(row["as_of"])
    return rows


async def _load_quotes(
    db: AsyncSession, codes: list[str], start: date, end: date
) -> dict[str, list[tuple[date, float]]]:
    if not codes:
        return {}
    aliases = sorted({alias for code in codes for alias in _code_aliases(code)})
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
        {"start": start, "end": end, "codes": aliases},
    )
    raw: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in result.mappings().all():
        price = _number(row["close_price"])
        if price:
            raw[str(row["security_code"])].append((_date_value(row["price_date"]), price))
    # 映射回持仓代码（BIL.US ← BIL）
    out: dict[str, list[tuple[date, float]]] = {}
    for code in codes:
        series = raw.get(code)
        if not series:
            for alias in _code_aliases(code):
                if alias in raw:
                    series = raw[alias]
                    break
        if series:
            out[code] = series
    return out


async def _load_nav(db: AsyncSession, fund_id: str, start: date, end: date) -> list[tuple[date, float]]:
    result = await db.execute(
        text(
            """
            SELECT evaluate_date, COALESCE(net_asset, unit_nav) AS value
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date BETWEEN :start AND :end
            ORDER BY evaluate_date
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    points = []
    for row in result.mappings().all():
        value = _number(row["value"])
        if value:
            points.append((_date_value(row["evaluate_date"]), value))
    return points


async def _load_pnl(db: AsyncSession, fund_id: str, start: date, end: date) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT security_code,
                   COALESCE(asset_class::text, 'OTHER') AS asset,
                   SUM(COALESCE(net_pnl_base, net_pnl, 0)) AS net_pnl
            FROM fsi.transact_pnl_item
            WHERE port_id = :fund_id
              AND evaluate_date BETWEEN :start AND :end
              AND security_code IS NOT NULL
            GROUP BY security_code, COALESCE(asset_class::text, 'OTHER')
            """
        ),
        {"fund_id": fund_id, "start": start, "end": end},
    )
    return [dict(row) for row in result.mappings().all()]


def _code_aliases(code: str) -> list[str]:
    aliases = [code]
    if "." in code:
        aliases.append(code.split(".", 1)[0])
    return aliases


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


def _holdings_as_of(holdings: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    dated = [row for row in holdings if row["as_of"] <= day]
    if not dated:
        # 区间早于首个持仓快照：用最早快照近似期初权重
        if not holdings:
            return []
        first = min(row["as_of"] for row in holdings)
        return [row for row in holdings if row["as_of"] == first]
    latest = max(row["as_of"] for row in dated)
    return [row for row in dated if row["as_of"] == latest]


def _static_period_rows(
    holdings: list[dict[str, Any]],
    quotes: dict[str, list[tuple[date, float]]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    snap = _holdings_as_of(holdings, start) or _holdings_as_of(holdings, end)
    rows = []
    for item in snap:
        code = str(item["security_code"])
        series = quotes.get(code, [])
        ret = _period_return(series, start, end)
        if not series and item.get("price"):
            ret = 0.0
        rows.append(
            {
                "date": end,
                "symbol": code,
                "security_name": item.get("security_name") or code,
                "weight": _number(item.get("weight")),
                "return_period": ret,
                "asset": item.get("asset") or "其他",
                "industry": item.get("industry") or "未分类",
            }
        )
    return rows


def _daily_rows(
    holdings: list[dict[str, Any]],
    quotes: dict[str, list[tuple[date, float]]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """每日 C_i,t = W_i,t-1 × R_i,t；权重按最近估值日持仓向前填充。"""
    trading_days = sorted(
        {
            day
            for series in quotes.values()
            for day, _ in series
            if start <= day <= end
        }
    )
    if len(trading_days) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for begin, finish in zip(trading_days, trading_days[1:]):
        snap = _holdings_as_of(holdings, begin) or _holdings_as_of(holdings, finish)
        for item in snap:
            code = str(item["security_code"])
            series = quotes.get(code, [])
            ret = _period_return(series, begin, finish)
            rows.append(
                {
                    "date": finish,
                    "symbol": code,
                    "security_name": item.get("security_name") or code,
                    "weight": _number(item.get("weight")),
                    "return_period": ret,
                    "asset": item.get("asset") or "其他",
                    "industry": item.get("industry") or "未分类",
                }
            )
    return rows


def _pnl_rows(
    holdings: list[dict[str, Any]],
    pnl_rows: list[dict[str, Any]],
    begin_nav: float,
    as_of: date,
) -> list[dict[str, Any]]:
    if not pnl_rows or not begin_nav:
        return []
    snap = {str(row["security_code"]): row for row in _holdings_as_of(holdings, as_of)}
    out = []
    for row in pnl_rows:
        code = str(row["security_code"])
        pnl = _number(row.get("net_pnl"))
        held = snap.get(code, {})
        mv = _number(held.get("market_value"))
        weight = mv / begin_nav if mv and begin_nav else _number(held.get("weight"))
        ret = (pnl / mv) if mv else 0.0
        # 无市值时直接用贡献反推：W*R = pnl/nav
        if not mv and begin_nav:
            weight = abs(pnl) / begin_nav if pnl else 0.0
            ret = 1.0 if pnl >= 0 else -1.0
            if weight == 0:
                continue
        out.append(
            {
                "date": as_of,
                "symbol": code,
                "security_name": held.get("security_name") or code,
                "weight": weight,
                "return_period": ret,
                "asset": _map_asset(str(row.get("asset") or held.get("asset") or "其他")),
                "industry": held.get("industry") or "未分类",
            }
        )
    return out


def _map_asset(asset: str) -> str:
    upper = asset.upper()
    if upper in {"STOCK", "EQUITY"} or asset == "股票":
        return "股票"
    if upper in {"BOND", "FI"} or asset == "债券":
        return "债券"
    return asset or "其他"
