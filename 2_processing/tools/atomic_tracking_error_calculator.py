"""基金組合跟蹤誤差 (Tracking Error) 計算器 (Atomic Tracking Error Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_tracking_error.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicTrackingErrorRecord:
    fund_id: str
    benchmark_code: str
    start_date: date
    end_date: date
    trading_days_count: int
    avg_daily_excess_return_pct: float
    daily_tracking_error_pct: float
    annualized_tracking_error_252_pct: float
    annualized_tracking_error_365_pct: float


async def compute_atomic_tracking_error(
    fund_id: str,
    benchmark_code: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicTrackingErrorRecord]:
    """執行基金組合跟蹤誤差 (Tracking Error) 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "bm_code": benchmark_code,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()

    if not row or row.trading_days_count == 0:
        logger.warning("No position or benchmark data found for tracking error calculation.")
        return None

    return AtomicTrackingErrorRecord(
        fund_id=str(row.fund_id),
        benchmark_code=str(row.benchmark_code),
        start_date=row.start_date,
        end_date=row.end_date,
        trading_days_count=int(row.trading_days_count),
        avg_daily_excess_return_pct=float(row.avg_daily_excess_return_pct or 0.0),
        daily_tracking_error_pct=float(row.daily_tracking_error_pct or 0.0),
        annualized_tracking_error_252_pct=float(row.annualized_tracking_error_252_pct or 0.0),
        annualized_tracking_error_365_pct=float(row.annualized_tracking_error_365_pct or 0.0),
    )