"""原子指標計算器：區間累積複利收益率 (%)。"""
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
SQL_FILE_PATH = Path(__file__).parent / "atomic_cumulative_return.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class CumulativeReturnRecord:
    fund_id: str
    start_date: date
    end_date: date
    start_nav: float
    end_nav: float
    sample_size: int
    cumulative_return_pct: Optional[float]


async def compute_atomic_cumulative_return(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[CumulativeReturnRecord]:
    """讀取 SQL 檔案並計算原子指標：區間累積複利收益率 (%)。

    Args:
        fund_id: 基金/組合 ID
        start_date: 區間起始日
        end_date: 區間截止日
        db: AsyncSession 資料庫連線

    Returns:
        Optional[CumulativeReturnRecord]: 區間累積複利收益率結果物件，若無資料則傳回 None
    """
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

    if not row or row.start_nav is None:
        logger.warning(
            "No NAV data found for cumulative return: fund_id=%s, start=%s, end=%s",
            fund_id,
            start_date,
            end_date,
        )
        return None

    return CumulativeReturnRecord(
        fund_id=row.fund_id,
        start_date=row.start_date,
        end_date=row.end_date,
        start_nav=float(row.start_nav),
        end_nav=float(row.end_nav),
        sample_size=int(row.sample_size),
        cumulative_return_pct=float(row.cumulative_return_pct)
        if row.cumulative_return_pct is not None
        else None,
    )