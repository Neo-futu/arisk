"""基金組合加權估值指標 (P/E, P/B, P/S) 計算器。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_weighted_valuation_ratios.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicWeightedValuationRatiosRecord:
    fund_id: str
    as_of_date: date
    pe_coverage_pct: float
    pb_coverage_pct: float
    ps_coverage_pct: float
    weighted_pe_arithmetic: float
    weighted_pe_harmonic: float
    weighted_pb_arithmetic: float
    weighted_pb_harmonic: float
    weighted_ps_arithmetic: float
    weighted_ps_harmonic: float


async def compute_atomic_weighted_valuation_ratios(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicWeightedValuationRatiosRecord]:
    """執行基金組合加權市盈率/市淨率/市銷率計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row:
        logger.warning("No valuation data found for the given fund and date.")
        return None

    return AtomicWeightedValuationRatiosRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        pe_coverage_pct=float(row.pe_coverage_pct or 0.0),
        pb_coverage_pct=float(row.pb_coverage_pct or 0.0),
        ps_coverage_pct=float(row.ps_coverage_pct or 0.0),
        weighted_pe_arithmetic=float(row.weighted_pe_arithmetic or 0.0),
        weighted_pe_harmonic=float(row.weighted_pe_harmonic or 0.0),
        weighted_pb_arithmetic=float(row.weighted_pb_arithmetic or 0.0),
        weighted_pb_harmonic=float(row.weighted_pb_harmonic or 0.0),
        weighted_ps_arithmetic=float(row.weighted_ps_arithmetic or 0.0),
        weighted_ps_harmonic=float(row.weighted_ps_harmonic or 0.0),
    )