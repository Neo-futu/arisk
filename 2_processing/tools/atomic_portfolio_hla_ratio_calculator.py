"""高流動性資產佔比 (High Liquidity Assets Ratio) 計算器 (Atomic Portfolio HLA Ratio Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_hla_ratio.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioHlaRatioRecord:
    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    hla_1day_amount_hkd: float
    hla_5day_amount_hkd: float
    hla_1day_ratio_pct: float
    hla_5day_ratio_pct: float


async def compute_atomic_portfolio_hla_ratio(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioHlaRatioRecord]:
    """執行高流動性資產佔比 (1日及5日) 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.total_nav_hkd == 0:
        logger.warning("No NAV or position data found for HLA ratio calculation.")
        return None

    return AtomicPortfolioHlaRatioRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        hla_1day_amount_hkd=float(row.hla_1day_amount_hkd or 0.0),
        hla_5day_amount_hkd=float(row.hla_5day_amount_hkd or 0.0),
        hla_1day_ratio_pct=float(row.hla_1day_ratio_pct or 0.0),
        hla_5day_ratio_pct=float(row.hla_5day_ratio_pct or 0.0),
    )
    