"""日均佔資產淨值 (%) 計算器 (Atomic Avg NAV Ratio Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_avg_nav_ratio.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicAvgNavRatioRecord:
    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    holding_days: int
    total_trading_days: int
    avg_nav_ratio_holding_period_pct: float
    avg_nav_ratio_full_period_pct: float


async def compute_atomic_avg_nav_ratio(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> List[AtomicAvgNavRatioRecord]:
    """執行日均佔資產淨值 (%) 算術平均值計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    rows = (
        await db.execute(
            text(sql_query),
            {
                "fid": fund_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    ).fetchall()

    if not rows:
        logger.warning("No position data found for average NAV ratio calculation.")
        return []

    return [
        AtomicAvgNavRatioRecord(
            fund_id=str(r.fund_id),
            start_date=r.start_date,
            end_date=r.end_date,
            security_code=str(r.security_code),
            security_name=str(r.security_name),
            holding_days=int(r.holding_days),
            total_trading_days=int(r.total_trading_days),
            avg_nav_ratio_holding_period_pct=float(r.avg_nav_ratio_holding_period_pct or 0.0),
            avg_nav_ratio_full_period_pct=float(r.avg_nav_ratio_full_period_pct or 0.0),
        )
        for r in rows
    ]