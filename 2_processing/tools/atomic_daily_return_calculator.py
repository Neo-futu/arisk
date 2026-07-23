"""原子指標計算器：日收益率 (%)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_daily_return.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class DailyReturnRecord:
    fund_id: str
    as_of_date: date
    total_nav: float
    prev_nav: Optional[float]
    daily_return_pct: Optional[float]


async def compute_atomic_daily_return(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    lookback_days: int = 252,
) -> List[DailyReturnRecord]:
    """讀取 SQL 檔案並計算原子指標：日收益率 (%)。

    Args:
        fund_id: 基金/組合 ID
        as_of_date: 計算基準日
        db: AsyncSession 資料庫連線
        lookback_days: 回溯天數 (預設 252)

    Returns:
        List[DailyReturnRecord]: 包含每日日收益率 (%) 的紀錄列表
    """
    start_date = as_of_date - timedelta(days=int(lookback_days * 1.5))
    sql_query = _load_sql_query(SQL_FILE_PATH)

    rows = (
        await db.execute(
            text(sql_query),
            {
                "fid": fund_id,
                "start_date": start_date,
                "end_date": as_of_date,
            },
        )
    ).fetchall()

    if not rows:
        logger.warning("No NAV data found for atomic daily return: fund_id=%s", fund_id)
        return []

    return [
        DailyReturnRecord(
            fund_id=r.fund_id,
            as_of_date=r.as_of_date,
            total_nav=float(r.total_nav),
            prev_nav=float(r.prev_nav) if r.prev_nav is not None else None,
            daily_return_pct=float(r.daily_return_pct) if r.daily_return_pct is not None else None,
        )
        for r in rows
    ]