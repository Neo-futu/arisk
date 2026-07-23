"""基金組合基點價值 (DV01) 計算器 (Atomic Portfolio DV01 Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_dv01.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioDv01Record:
    fund_id: str
    as_of_date: date
    total_portfolio_nav: float
    total_bond_mv: float
    bond_weight_pct: float
    portfolio_dv01_hkd: float
    dv01_per_million_nav_hkd: float


async def compute_atomic_portfolio_dv01(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioDv01Record]:
    """執行基金組合基點價值 (DV01) 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.total_portfolio_nav == 0:
        logger.warning("No position or duration data found for DV01 calculation.")
        return None

    return AtomicPortfolioDv01Record(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_portfolio_nav=float(row.total_portfolio_nav or 0.0),
        total_bond_mv=float(row.total_bond_mv or 0.0),
        bond_weight_pct=float(row.bond_weight_pct or 0.0),
        portfolio_dv01_hkd=float(row.portfolio_dv01_hkd or 0.0),
        dv01_per_million_nav_hkd=float(row.dv01_per_million_nav_hkd or 0.0),
    )