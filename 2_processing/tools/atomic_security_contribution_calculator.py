"""個股/個券每日收益累計與區間貢獻計算器 (Atomic Security Contribution Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_security_contribution.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicSecurityContributionRecord:
    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    avg_weight_pct: float
    simple_sum_contrib_pct: float
    cumulative_contrib_pct: float


async def compute_atomic_security_contribution(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> List[AtomicSecurityContributionRecord]:
    """執行單券每日收益累計與區間貢獻計算。"""
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
        logger.warning("No position data found for atomic security contribution calculation.")
        return []

    return [
        AtomicSecurityContributionRecord(
            fund_id=str(r.fund_id),
            start_date=r.start_date,
            end_date=r.end_date,
            security_code=str(r.security_code),
            security_name=str(r.security_name),
            avg_weight_pct=float(r.avg_weight_pct),
            simple_sum_contrib_pct=float(r.simple_sum_contrib_pct),
            cumulative_contrib_pct=float(r.cumulative_contrib_pct),
        )
        for r in rows
    ]