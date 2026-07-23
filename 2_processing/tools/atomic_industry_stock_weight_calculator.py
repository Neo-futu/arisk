"""原子指標計算器：某行業佔股票市值比 (%)。"""
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
SQL_FILE_PATH = Path(__file__).parent / "atomic_industry_stock_weight.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class IndustryStockWeightRecord:
    fund_id: str
    as_of_date: date
    industry_name: str
    industry_stock_mv_hkd: float
    total_stock_mv: float
    industry_stock_weight_pct: Optional[float]


async def compute_atomic_industry_stock_weight(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> List[IndustryStockWeightRecord]:
    """讀取 SQL 檔案並計算原子指標：某行業佔股票市值比 (%)。

    Args:
        fund_id: 基金/組合 ID
        as_of_date: 計算基準日
        db: AsyncSession 資料庫連線

    Returns:
        List[IndustryStockWeightRecord]: 包含各行業股票市值及佔全部股票市值比例的紀錄列表
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
            "No stock position data found for industry weight: fund_id=%s, as_of_date=%s",
            fund_id,
            as_of_date,
        )
        return []

    return [
        IndustryStockWeightRecord(
            fund_id=str(r.fund_id),
            as_of_date=r.as_of_date,
            industry_name=str(r.industry_name),
            industry_stock_mv_hkd=float(r.industry_stock_mv_hkd),
            total_stock_mv=float(r.total_stock_mv),
            industry_stock_weight_pct=float(r.industry_stock_weight_pct)
            if r.industry_stock_weight_pct is not None
            else None,
        )
        for r in rows
    ]