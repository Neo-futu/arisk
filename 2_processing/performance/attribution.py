"""業績歸因：Brinson-Hood-Beebower (BHB) 模型。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class AttributionResult:
    fund_id: str
    period_start: date
    period_end: date
    fund_return: float
    benchmark_return: float
    active_return: float
    allocation_effect: float       # 配置效應
    selection_effect: float        # 選股效應
    interaction_effect: float      # 交互效應
    by_sector: list[dict]          # 按行業分解


async def compute_attribution(
    fund_id: str,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> AttributionResult:
    """計算 BHB 業績歸因。"""
    # 取基金及基準收益
    fund_ret = await _get_period_return(fund_id, period_start, period_end, db)
    benchmark_id = await _get_benchmark_id(fund_id, db)
    bench_ret = await _get_period_return(benchmark_id, period_start, period_end, db) if benchmark_id else 0.0

    # 取各行業權重和收益
    fund_sectors = await _get_sector_returns(fund_id, period_start, period_end, db)
    bench_sectors = await _get_sector_returns(benchmark_id or "", period_start, period_end, db)

    allocation = 0.0
    selection = 0.0
    interaction = 0.0
    by_sector: list[dict] = []

    all_sectors = set(fund_sectors) | set(bench_sectors)
    for sector in all_sectors:
        fw, fr = fund_sectors.get(sector, (0.0, 0.0))
        bw, br = bench_sectors.get(sector, (0.0, 0.0))

        alloc_effect = (fw - bw) * (br - bench_ret)
        sel_effect = bw * (fr - br)
        inter_effect = (fw - bw) * (fr - br)

        allocation += alloc_effect
        selection += sel_effect
        interaction += inter_effect

        by_sector.append({
            "sector": sector,
            "fund_weight": fw,
            "bench_weight": bw,
            "fund_return": fr,
            "bench_return": br,
            "allocation_effect": alloc_effect,
            "selection_effect": sel_effect,
            "interaction_effect": inter_effect,
        })

    return AttributionResult(
        fund_id=fund_id,
        period_start=period_start,
        period_end=period_end,
        fund_return=fund_ret,
        benchmark_return=bench_ret,
        active_return=fund_ret - bench_ret,
        allocation_effect=allocation,
        selection_effect=selection,
        interaction_effect=interaction,
        by_sector=sorted(by_sector, key=lambda x: abs(x["allocation_effect"]), reverse=True),
    )


async def _get_period_return(entity_id: str, start: date, end: date, db: AsyncSession) -> float:
    row = await db.execute(
        text("""
            SELECT
                (MAX(nav_per_unit) FILTER (WHERE nav_date = :end) /
                 MAX(nav_per_unit) FILTER (WHERE nav_date = :start) - 1) AS period_return
            FROM fsi.nav_history
            WHERE fund_id = :fid AND nav_date IN (:start, :end)
        """),
        {"fid": entity_id, "start": start, "end": end},
    )
    result = row.fetchone()
    return float(result[0]) if result and result[0] is not None else 0.0


async def _get_benchmark_id(fund_id: str, db: AsyncSession) -> str | None:
    row = await db.execute(
        text("SELECT benchmark_id FROM fsi.funds WHERE fund_id = :fid"),
        {"fid": fund_id},
    )
    r = row.fetchone()
    return r[0] if r else None


async def _get_sector_returns(
    entity_id: str, start: date, end: date, db: AsyncSession
) -> dict[str, tuple[float, float]]:
    """返回 {sector: (weight, return)}"""
    rows = await db.execute(
        text("""
            SELECT sector, AVG(weight_pct) / 100 AS avg_weight,
                   0.0 AS sector_return  -- 簡化：需接市場數據計算
            FROM fsi.positions
            WHERE fund_id = :fid AND as_of_date BETWEEN :start AND :end
            GROUP BY sector
        """),
        {"fid": entity_id, "start": start, "end": end},
    )
    return {r.sector: (float(r.avg_weight or 0), float(r.sector_return or 0)) for r in rows}
