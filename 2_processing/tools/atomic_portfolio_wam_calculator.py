"""貨幣基金組合加權平均剩餘期限 (WAM) 計算器 (Atomic Portfolio WAM Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_wam.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioWamRecord:
    fund_id: str
    as_of_date: date
    total_portfolio_nav: float
    total_mmf_mv: float
    mmf_weight_pct: float
    wam_days_mmf_only: float
    wam_years_mmf_only: float
    wam_days_total_nav: float


async def compute_atomic_portfolio_wam(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioWamRecord]:
    """執行貨幣基金組合加權平均剩餘期限 (WAM) 計算。"""
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
        logger.warning("No position or maturity data found for WAM calculation.")
        return None

    return AtomicPortfolioWamRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_portfolio_nav=float(row.total_portfolio_nav or 0.0),
        total_mmf_mv=float(row.total_mmf_mv or 0.0),
        mmf_weight_pct=float(row.mmf_weight_pct or 0.0),
        wam_days_mmf_only=float(row.wam_days_mmf_only or 0.0),
        wam_years_mmf_only=float(row.wam_years_mmf_only or 0.0),
        wam_days_total_nav=float(row.wam_days_total_nav or 0.0),
    )