"""正/逆回購佔比 (Repo & Reverse Repo Exposure Ratios) 計算器 (Atomic Repo Exposure Ratio Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_repo_exposure_ratio.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicRepoExposureRatioRecord:
    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    total_repo_amount_hkd: float
    total_reverse_repo_amount_hkd: float
    repo_ratio_pct: float
    reverse_repo_ratio_pct: float
    net_repo_ratio_pct: float


async def compute_atomic_repo_exposure_ratio(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicRepoExposureRatioRecord]:
    """執行正/逆回購佔比計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.total_nav_hkd == 0:
        logger.warning("No NAV or position data found for repo exposure calculation.")
        return None

    return AtomicRepoExposureRatioRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        total_repo_amount_hkd=float(row.total_repo_amount_hkd or 0.0),
        total_reverse_repo_amount_hkd=float(row.total_reverse_repo_amount_hkd or 0.0),
        repo_ratio_pct=float(row.repo_ratio_pct or 0.0),
        reverse_repo_ratio_pct=float(row.reverse_repo_ratio_pct or 0.0),
        net_repo_ratio_pct=float(row.net_repo_ratio_pct or 0.0),
    )