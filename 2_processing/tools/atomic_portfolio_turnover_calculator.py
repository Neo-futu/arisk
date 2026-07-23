"""基金組合年換手率 (Annualized Portfolio Turnover Rate) 計算器 (Atomic Portfolio Turnover Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_turnover.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioTurnoverRecord:
    fund_id: str
    start_date: date
    end_date: date
    days_in_period: int
    avg_net_asset_value_hkd: float
    total_purchases_hkd: float
    total_sales_hkd: float
    turnover_base_amount_hkd: float
    period_turnover_rate_pct: float
    annualized_turnover_rate_pct: float


async def compute_atomic_portfolio_turnover(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioTurnoverRecord]:
    """執行基金組合年換手率計算。"""
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

    if not row or row.avg_net_asset_value_hkd == 0:
        logger.warning("No NAV or transaction data found for portfolio turnover calculation.")
        return None

    return AtomicPortfolioTurnoverRecord(
        fund_id=str(row.fund_id),
        start_date=row.start_date,
        end_date=row.end_date,
        days_in_period=int(row.days_in_period),
        avg_net_asset_value_hkd=float(row.avg_net_asset_value_hkd or 0.0),
        total_purchases_hkd=float(row.total_purchases_hkd or 0.0),
        total_sales_hkd=float(row.total_sales_hkd or 0.0),
        turnover_base_amount_hkd=float(row.turnover_base_amount_hkd or 0.0),
        period_turnover_rate_pct=float(row.period_turnover_rate_pct or 0.0),
        annualized_turnover_rate_pct=float(row.annualized_turnover_rate_pct or 0.0),
    )