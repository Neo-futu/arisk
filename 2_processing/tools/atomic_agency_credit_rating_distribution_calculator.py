"""基金組合按評級機構分劃信用評級分布占比 (%) 計算器 (Atomic Agency Credit Rating Distribution Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_agency_credit_rating_distribution.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AgencyRatingItem:
    rating_agency: str
    rating_agency_name: str
    credit_rating: str
    rating_market_value_hkd: float
    nav_weight_pct: float
    total_bond_weight_pct: float
    agency_share_pct: float
    agency_sort_order: int
    rating_sort_order: int


@dataclass
class AtomicAgencyCreditRatingDistributionRecord:
    fund_id: str
    as_of_date: date
    ratings: List[AgencyRatingItem]


async def compute_atomic_agency_credit_rating_distribution(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicAgencyCreditRatingDistributionRecord]:
    """執行基金組合按評級機構分劃信用評級分布占比計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    rows = result.fetchall()

    if not rows:
        logger.warning("No position or agency rating data found for the given fund and date.")
        return None

    items = [
        AgencyRatingItem(
            rating_agency=str(row.rating_agency),
            rating_agency_name=str(row.rating_agency_name),
            credit_rating=str(row.credit_rating),
            rating_market_value_hkd=float(row.rating_market_value_hkd or 0.0),
            nav_weight_pct=float(row.nav_weight_pct or 0.0),
            total_bond_weight_pct=float(row.total_bond_weight_pct or 0.0),
            agency_share_pct=float(row.agency_share_pct or 0.0),
            agency_sort_order=int(row.agency_sort_order),
            rating_sort_order=int(row.rating_sort_order),
        )
        for row in rows
    ]

    return AtomicAgencyCreditRatingDistributionRecord(
        fund_id=fund_id,
        as_of_date=as_of_date,
        ratings=items,
    )