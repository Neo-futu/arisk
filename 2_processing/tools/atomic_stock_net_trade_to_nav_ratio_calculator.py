"""淨交易佔淨值比例 (Net Trade Amount to Average NAV Ratio) 計算器 (Atomic Stock Net Trade To NAV Ratio Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_stock_net_trade_to_nav_ratio.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicStockNetTradeToNavRatioRecord:
    fund_id: str
    security_code: str
    start_date: date
    end_date: date
    avg_net_asset_value_hkd: float
    total_buy_amount_hkd: float
    total_sell_amount_hkd: float
    net_trade_amount_hkd: float
    net_trade_to_nav_ratio_pct: float


async def compute_atomic_stock_net_trade_to_nav_ratio(
    fund_id: str,
    security_code: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> Optional[AtomicStockNetTradeToNavRatioRecord]:
    """執行單個股票淨交易佔淨值比例計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "security_code": security_code,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()

    if not row or row.avg_net_asset_value_hkd == 0:
        logger.warning("No NAV or transaction data found for net trade ratio calculation.")
        return None

    return AtomicStockNetTradeToNavRatioRecord(
        fund_id=str(row.fund_id),
        security_code=str(row.security_code),
        start_date=row.start_date,
        end_date=row.end_date,
        avg_net_asset_value_hkd=float(row.avg_net_asset_value_hkd or 0.0),
        total_buy_amount_hkd=float(row.total_buy_amount_hkd or 0.0),
        total_sell_amount_hkd=float(row.total_sell_amount_hkd or 0.0),
        net_trade_amount_hkd=float(row.net_trade_amount_hkd or 0.0),
        net_trade_to_nav_ratio_pct=float(row.net_trade_to_nav_ratio_pct or 0.0),
    )
    