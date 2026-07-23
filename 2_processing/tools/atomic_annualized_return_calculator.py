"""年化收益率 (%) 計算器 (Atomic Annualized Return Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_annualized_return.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicAnnualizedReturnRecord:
    fund_id: str
    start_date: date
    end_date: date
    natural_days: int
    trading_days: int
    cumulative_return_pct: float
    annualized_return_365_pct: float
    annualized_return_252_pct: float


async def compute_atomic_annualized_return(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicAnnualizedReturnRecord]:
    """執行年化收益率 (%) 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()

    if not row:
        logger.warning("No position data found for annualized return calculation.")
        return None

    return AtomicAnnualizedReturnRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        natural_days=int(row.natural_days),
        trading_days=int(row.trading_days),
        cumulative_return_pct=float(row.cumulative_return_pct or 0.0),
        annualized_return_365_pct=float(row.annualized_return_365_pct or 0.0),
        annualized_return_252_pct=float(row.annualized_return_252_pct or 0.0),
    )