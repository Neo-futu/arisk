"""最大回撤 (%) 計算器 (Atomic Max Drawdown Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_max_drawdown.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicMaxDrawdownRecord:
    fund_id: str
    start_date: date
    end_date: date
    max_drawdown_pct: float
    trough_date: Optional[date]
    trough_nav: float
    peak_nav: float


async def compute_atomic_max_drawdown(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicMaxDrawdownRecord]:
    """執行最大回撤 (%) 計算。"""
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
        logger.warning("No position data found for max drawdown calculation.")
        return None

    return AtomicMaxDrawdownRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        max_drawdown_pct=float(row.max_drawdown_pct or 0.0),
        trough_date=row.trough_date,
        trough_nav=float(row.trough_nav or 0.0),
        peak_nav=float(row.peak_nav or 0.0),
    )