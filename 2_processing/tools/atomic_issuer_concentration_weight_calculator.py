"""原子指標計算器：發行人集中度 (%)。"""
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
SQL_FILE_PATH = Path(__file__).parent / "atomic_issuer_concentration_weight.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class IssuerConcentrationWeightRecord:
    fund_id: str
    as_of_date: date
    issuer_id: str
    issuer_name: str
    issuer_mv_hkd: float
    total_nav: float
    concentration_pct: Optional[float]


async def compute_atomic_issuer_concentration_weight(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> List[IssuerConcentrationWeightRecord]:
    """讀取 SQL 檔案並計算原子指標：發行人集中度 (%)。

    Args:
        fund_id: 基金/組合 ID
        as_of_date: 計算基準日
        db: AsyncSession 資料庫連線

    Returns:
        List[IssuerConcentrationWeightRecord]: 包含各發行人總市值及 NAV 佔比的紀錄列表
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
            "No position data found for issuer concentration: fund_id=%s, as_of_date=%s",
            fund_id,
            as_of_date,
        )
        return []

    return [
        IssuerConcentrationWeightRecord(
            fund_id=str(r.fund_id),
            as_of_date=r.as_of_date,
            issuer_id=str(r.issuer_id),
            issuer_name=str(r.issuer_name),
            issuer_mv_hkd=float(r.issuer_mv_hkd),
            total_nav=float(r.total_nav),
            concentration_pct=float(r.concentration_pct) if r.concentration_pct is not None else None,
        )
        for r in rows
    ]