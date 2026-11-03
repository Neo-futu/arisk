"""指数 / 基准：``fsi.mktdata_index_quotes`` + ``fsi.para_portfolio_benchmark``。

持仓与个券行情仍在 ``asof``；本模块只补组合主基准的指数水平与日收益，
供 Beta / Tracking Error / 因子风险使用。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def daily_returns(levels: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Close-to-close simple returns from ordered index levels."""

    out: list[tuple[date, float]] = []
    previous: float | None = None
    for when, level in levels:
        value = float(level)
        if previous is not None and previous > 0:
            out.append((when, value / previous - 1.0))
        previous = value
    return out


def return_values(levels_or_returns: list[tuple[date, float]] | list[float]) -> list[float]:
    if not levels_or_returns:
        return []
    first = levels_or_returns[0]
    if isinstance(first, tuple):
        return [float(item[1]) for item in levels_or_returns]  # type: ignore[index]
    return [float(item) for item in levels_or_returns]


async def resolve_benchmark_id(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    *,
    benchmark_id: str | None = None,
) -> str | None:
    """Explicit code wins; else PRIMARY row on ``fsi.para_portfolio_benchmark``."""

    chosen = (benchmark_id or "").strip() or None
    if chosen:
        return chosen
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
    value = result.scalar_one_or_none()
    return str(value) if value else None


async def load_index_levels(
    db: AsyncSession,
    index_code: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    result = await db.execute(
        text(
            """
            SELECT price_date, close_price
            FROM fsi.mktdata_index_quotes
            WHERE index_code = :index_code
              AND price_date BETWEEN :start AND :end
              AND close_price IS NOT NULL
            ORDER BY price_date
            """
        ),
        {"index_code": index_code, "start": start, "end": end},
    )
    rows: list[tuple[date, float]] = []
    for price_date, close_price in result.all():
        when = price_date if isinstance(price_date, date) else date.fromisoformat(str(price_date)[:10])
        rows.append((when, float(close_price)))
    return rows


async def load_benchmark_pack(
    db: AsyncSession,
    snapshot: Any,
    *,
    lookback_days: int = 500,
    benchmark_id: str | None = None,
) -> dict[str, Any]:
    """Resolve fund benchmark and load index history for RiskEngine KPIs."""

    fund_id = str(getattr(snapshot, "fund_id", "") or "")
    as_of = getattr(snapshot, "as_of_date")
    start = as_of - timedelta(days=max(int(lookback_days), 2))
    code = await resolve_benchmark_id(db, fund_id, as_of, benchmark_id=benchmark_id)
    if not code:
        return {
            "benchmark_id": None,
            "index_levels": [],
            "benchmark_returns": [],
            "source_table": "fsi.mktdata_index_quotes",
            "warnings": [f"{fund_id}: 无主基准（para_portfolio_benchmark）"],
        }
    levels = await load_index_levels(db, code, start, as_of)
    returns = daily_returns(levels)
    warnings: list[str] = []
    if len(levels) < 3:
        warnings.append(f"基准 {code}: mktdata_index_quotes 样本不足（{len(levels)}）")
    return {
        "benchmark_id": code,
        "index_levels": levels,
        "benchmark_returns": returns,
        "source_table": "fsi.mktdata_index_quotes",
        "warnings": warnings,
    }


def attach_benchmark(snapshot: Any, pack: dict[str, Any]) -> Any:
    """Attach benchmark series onto the existing snapshot (no second store)."""

    snapshot.benchmark_id = pack.get("benchmark_id")
    levels = list(pack.get("index_levels") or [])
    returns = list(pack.get("benchmark_returns") or [])
    snapshot.index_levels = levels
    snapshot.benchmark_returns = return_values(returns)
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    market = dict(quality.get("market") or {})
    market["benchmark_id"] = snapshot.benchmark_id
    market["index_level_count"] = len(levels)
    market["benchmark_return_count"] = len(snapshot.benchmark_returns)
    if pack.get("source_table"):
        tables = list(market.get("source_tables") or [])
        if pack["source_table"] not in tables:
            tables.append(str(pack["source_table"]))
        market["source_tables"] = tables
    warnings = list(market.get("warnings") or [])
    warnings.extend(list(pack.get("warnings") or []))
    market["warnings"] = warnings
    quality["market"] = market
    quality["benchmark_id"] = snapshot.benchmark_id
    snapshot.data_quality = quality

    panel = getattr(snapshot, "market_panel", None)
    if panel is not None:
        panel.benchmark_id = snapshot.benchmark_id
        panel.index_levels = {when.isoformat(): level for when, level in levels}
        panel.benchmark_returns = list(snapshot.benchmark_returns)
        if pack.get("source_table") and pack["source_table"] not in panel.source_tables:
            panel.source_tables = sorted({*panel.source_tables, str(pack["source_table"])})
        panel.warnings.extend(list(pack.get("warnings") or []))
    return snapshot
