"""組合變現天數 (Days to Liquidate Portfolio) 計算器 (Atomic Portfolio Days To Liquidate Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_days_to_liquidate.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioDaysToLiquidateRecord:
    fund_id: str
    as_of_date: date
    total_nav_hkd: float
    total_position_market_value_hkd: float
    adv_participation_rate_parameter: float
    max_days_to_liquidate: float
    weighted_avg_days_to_liquidate: float


async def compute_atomic_portfolio_days_to_liquidate(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    adv_participation_rate: float = 0.20,
) -> Optional[AtomicPortfolioDaysToLiquidateRecord]:
    """執行組合變現天數計算。

    Args:
        fund_id: 基金代號
        as_of_date: 計算基準日
        db: AsyncSession 數據庫連線物件
        adv_participation_rate: 假定佔市場日均成交量之最高比例（預設 20% 即 0.20）
    """
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "as_of_date": as_of_date,
            "adv_participation_rate": adv_participation_rate,
        },
    )
    row = result.fetchone()

    if not row or row.total_nav_hkd == 0:
        logger.warning("No NAV or market liquidity data found for liquidation days calculation.")
        return None

    return AtomicPortfolioDaysToLiquidateRecord(
        fund_id=str(row.fund_id),
        as_of_date=row.as_of_date,
        total_nav_hkd=float(row.total_nav_hkd or 0.0),
        total_position_market_value_hkd=float(row.total_position_market_value_hkd or 0.0),
        adv_participation_rate_parameter=float(row.adv_participation_rate_parameter or adv_participation_rate),
        max_days_to_liquidate=float(row.max_days_to_liquidate or 0.0),
        weighted_avg_days_to_liquidate=float(row.weighted_avg_days_to_liquidate or 0.0),
    )
    