"""原子指標計算器：大類資產收益貢獻 (%)。"""
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
SQL_FILE_PATH = Path(__file__).parent / "atomic_asset_class_return_contribution.sql"


def _load_sql_query(file_path: Path) -> str:
    """從檔案載入 SQL 語句。"""
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AssetClassReturnContributionRecord:
    fund_id: str
    start_date: date
    end_date: date
    asset_class: str
    total_pnl_hkd: float
    initial_nav: float
    return_contribution_pct: Optional[float]


async def compute_atomic_asset_class_return_contribution(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> List[AssetClassReturnContributionRecord]:
    """讀取 SQL 檔案並計算原子指標：大類資產收益貢獻 (%)。

    Args:
        fund_id: 基金/組合 ID
        start_date: 計算區間起始日
        end_date: 計算區間截止日
        db: AsyncSession 資料庫連線

    Returns:
        List[AssetClassReturnContributionRecord]: 包含各資產大類損益及對組合總收益率的拉動點數紀錄列表
    """
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
        logger.warning(
            "No PnL or NAV data found for asset class return contribution: fund_id=%s, range=[%s, %s]",
            fund_id,
            start_date,
            end_date,
        )
        return []

    return [
        AssetClassReturnContributionRecord(
            fund_id=str(r.fund_id),
            start_date=r.start_date,
            end_date=r.end_date,
            asset_class=str(r.asset_class),
            total_pnl_hkd=float(r.total_pnl_hkd),
            initial_nav=float(r.initial_nav),
            return_contribution_pct=float(r.return_contribution_pct)
            if r.return_contribution_pct is not None
            else None,
        )
        for r in rows
    ]