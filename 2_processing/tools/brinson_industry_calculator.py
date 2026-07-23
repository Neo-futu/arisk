"""行業層面 Brinson 歸因計算器。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "brinson_industry.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class BrinsonIndustryRecord:
    fund_id: str
    benchmark_id: str
    start_date: date
    end_date: date
    industry_name: str
    w_p: float
    w_b: float
    r_p: float
    r_b: float
    allocation_effect_pct: Optional[float]
    selection_effect_pct: Optional[float]
    interaction_effect_pct: Optional[float]
    total_excess_pct: Optional[float]


async def compute_brinson_industry(
    fund_id: str,
    benchmark_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> List[BrinsonIndustryRecord]:
    """執行行業層面 Brinson 歸因計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    rows = (
        await db.execute(
            text(sql_query),
            {
                "fid": fund_id,
                "benchmark_id": benchmark_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    ).fetchall()

    if not rows:
        logger.warning("No data found for Industry Brinson attribution.")
        return []

    return [
        BrinsonIndustryRecord(
            fund_id=str(r.fund_id),
            benchmark_id=str(r.benchmark_id),
            start_date=r.start_date,
            end_date=r.end_date,
            industry_name=str(r.industry_name),
            w_p=float(r.w_p),
            w_b=float(r.w_b),
            r_p=float(r.r_p),
            r_b=float(r.r_b),
            allocation_effect_pct=float(r.allocation_effect_pct) if r.allocation_effect_pct is not None else None,
            selection_effect_pct=float(r.selection_effect_pct) if r.selection_effect_pct is not None else None,
            interaction_effect_pct=float(r.interaction_effect_pct) if r.interaction_effect_pct is not None else None,
            total_excess_pct=float(r.total_excess_pct) if r.total_excess_pct is not None else None,
        )
        for r in rows
    ]