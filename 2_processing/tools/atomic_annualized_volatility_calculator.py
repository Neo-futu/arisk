"""年化波動率 (%) 計算器 (Atomic Annualized Volatility Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_annualized_volatility.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicAnnualizedVolatilityRecord:
    fund_id: str
    start_date: date
    end_date: date
    trading_days: int
    daily_volatility_pct: float
    annualized_volatility_252_pct: float
    annualized_volatility_365_pct: float


async def compute_atomic_annualized_volatility(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicAnnualizedVolatilityRecord]:
    """執行年化波動率 (%) 計算。"""
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
        logger.warning("No position data found for annualized volatility calculation.")
        return None

    return AtomicAnnualizedVolatilityRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        trading_days=int(row.trading_days),
        daily_volatility_pct=float(row.daily_volatility_pct or 0.0),
        annualized_volatility_252_pct=float(row.annualized_volatility_252_pct or 0.0),
        annualized_volatility_365_pct=float(row.annualized_volatility_365_pct or 0.0),
    )