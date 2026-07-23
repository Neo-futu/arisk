"""絕對收益 (億元) 計算器。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "absolute_return.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AbsoluteReturnRecord:
    fund_id: str
    start_date: date
    end_date: date
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_dividend_income: float
    total_absolute_return: float
    realized_pnl_yi: float
    unrealized_pnl_yi: float
    dividend_income_yi: float
    absolute_return_yi: float


async def compute_absolute_return(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AbsoluteReturnRecord]:
    """執行絕對收益 (億元) 計算。"""
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
        logger.warning("No position data found for absolute return calculation.")
        return None

    return AbsoluteReturnRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        total_realized_pnl=float(row.total_realized_pnl),
        total_unrealized_pnl=float(row.total_unrealized_pnl),
        total_dividend_income=float(row.total_dividend_income),
        total_absolute_return=float(row.total_absolute_return),
        realized_pnl_yi=float(row.realized_pnl_yi),
        unrealized_pnl_yi=float(row.unrealized_pnl_yi),
        dividend_income_yi=float(row.dividend_income_yi),
        absolute_return_yi=float(row.absolute_return_yi),
    )