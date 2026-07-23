"""原子指標計算器：板塊/細分資產配置比 (%)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 指向同目錄下的獨立 SQL 檔案
SQL_FILE_PATH = Path(__file__).parent / "atomic_sector_allocation_weight.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class SectorAllocationWeightRecord:
    fund_id: str
    as_of_date: date
    sector_name: str
    sector_mv_hkd: float
    total_nav: float
    weight_pct: Optional[float]


async def compute_atomic_sector_allocation_weight(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> List[SectorAllocationWeightRecord]:
    """讀取 SQL 檔案並計算原子指標：板塊/細分資產配置比 (%)。

    Args:
        fund_id: 基金/組合 ID
        as_of_date: 計算基準日
        db: AsyncSession 資料庫連線

    Returns:
        List[SectorAllocationWeightRecord]: 包含板塊市值及 NAV 佔比的紀錄列表
    """
    sql_query = _load_sql_query(SQL_FILE_PATH)

    rows = (
        await db.execute(
            text(sql_query),
            {
                "fid": fund_id,
                "as_of_date": as_of_date,
            },
        )
    ).fetchall()

    if not rows:
        logger.warning(
            "No position data found for sector allocation weight: fund_id=%s, as_of_date=%s",
            fund_id,
            as_of_date,
        )
        return []

    return [
        SectorAllocationWeightRecord(
            fund_id=str(r.fund_id),
            as_of_date=r.as_of_date,
            sector_name=str(r.sector_name),
            sector_mv_hkd=float(r.sector_mv_hkd),
            total_nav=float(r.total_nav),
            weight_pct=float(r.weight_pct) if r.weight_pct is not None else None,
        )
        for r in rows
    ]