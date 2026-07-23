"""基金總槓桿率 (Total Portfolio Leverage Ratio) 計算器 (Atomic Portfolio Leverage Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_leverage.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioLeverageRecord:
    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    total_gross_assets_hkd: float
    physical_asset_mv_hkd: float
    derivative_gross_notional_hkd: float
    total_gross_exposure_hkd: float
    gross_asset_leverage_pct: float
    gross_exposure_leverage_pct: float


async def compute_atomic_portfolio_leverage(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioLeverageRecord]:
    """執行基金總槓桿率計算。"""
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
        logger.warning("No NAV or exposure data found for leverage calculation.")
        return None

    return AtomicPortfolioLeverageRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        total_gross_assets_hkd=float(row.total_gross_assets_hkd or 0.0),
        physical_asset_mv_hkd=float(row.physical_asset_mv_hkd or 0.0),
        derivative_gross_notional_hkd=float(row.derivative_gross_notional_hkd or 0.0),
        total_gross_exposure_hkd=float(row.total_gross_exposure_hkd or 0.0),
        gross_asset_leverage_pct=float(row.gross_asset_leverage_pct or 0.0),
        gross_exposure_leverage_pct=float(row.gross_exposure_leverage_pct or 0.0),
    )