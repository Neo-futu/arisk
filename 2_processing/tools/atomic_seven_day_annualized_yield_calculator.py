"""原子指標計算器：七日年化收益率（貨幣 %）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_seven_day_annualized_yield.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class SevenDayAnnualizedYieldRecord:
    fund_id: str
    as_of_date: date
    sample_days: int
    seven_day_annualized_yield_pct: Optional[float]


async def compute_atomic_seven_day_annualized_yield(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[SevenDayAnnualizedYieldRecord]:
    """讀取 SQL 檔案並計算原子指標：七日年化收益率（貨幣 %）。

    Args:
        fund_id: 基金/組合 ID
        as_of_date: 計算基準日
        db: AsyncSession 資料庫連線

    Returns:
        Optional[SevenDayAnnualizedYieldRecord]: 七日年化收益率紀錄，若無資料或數據不足 7 日則七日年化值為 None
    """
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.as_of_date is None:
        logger.warning(
            "No NAV data found for seven day yield: fund_id=%s, as_of_date=%s",
            fund_id,
            as_of_date,
        )
        return None

    return SevenDayAnnualizedYieldRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        sample_days=int(row.sample_days),
        seven_day_annualized_yield_pct=float(row.seven_day_annualized_yield_pct)
        if row.seven_day_annualized_yield_pct is not None
        else None,
    )