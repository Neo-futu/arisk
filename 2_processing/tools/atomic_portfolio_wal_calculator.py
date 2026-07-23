
"""貨幣基金組合加權平均剩餘存續期 (WAL) 計算器 (Atomic Portfolio WAL Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_wal.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioWalRecord:
    fund_id: str
    as_of_date: date
    total_portfolio_nav: float
    total_mmf_mv: float
    mmf_weight_pct: float
    wal_days_mmf_only: float
    wal_years_mmf_only: float
    weighted_duration_years: float
    wal_days_total_nav: float


async def compute_atomic_portfolio_wal(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioWalRecord]:
    """執行貨幣基金組合加權平均剩餘存續期 (WAL) 及 Duration 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.total_portfolio_nav == 0:
        logger.warning("No position or analytics data found for WAL calculation.")
        return None

    return AtomicPortfolioWalRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_portfolio_nav=float(row.total_portfolio_nav or 0.0),
        total_mmf_mv=float(row.total_mmf_mv or 0.0),
        mmf_weight_pct=float(row.mmf_weight_pct or 0.0),
        wal_days_mmf_only=float(row.wal_days_mmf_only or 0.0),
        wal_years_mmf_only=float(row.wal_years_mmf_only or 0.0),
        weighted_duration_years=float(row.weighted_duration_years or 0.0),
        wal_days_total_nav=float(row.wal_days_total_nav or 0.0),
    )