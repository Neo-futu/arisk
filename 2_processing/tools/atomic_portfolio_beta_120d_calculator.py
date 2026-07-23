"""基金組合 Beta (近 120 個交易日) 計算器 (Atomic Portfolio Beta 120d Calculator)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "atomic_portfolio_beta_120d.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class AtomicPortfolioBeta120dRecord:
    fund_id: str
    benchmark_code: str
    window_start_date: date
    window_end_date: date
    trading_days_count: int
    avg_portfolio_return_pct: float
    avg_benchmark_return_pct: float
    var_benchmark: float
    cov_portfolio_benchmark: float
    beta_120d: float
    beta_regr_slope_120d: float
    r_squared_120d: float


async def compute_atomic_portfolio_beta_120d(
    fund_id: str,
    benchmark_code: str,
    as_of_date: date,
    db: AsyncSession,
) -> Optional[AtomicPortfolioBeta120dRecord]:
    """執行近 120 個交易日基金組合 Beta 計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    result = await db.execute(
        text(sql_query),
        {
            "fid": fund_id,
            "bm_code": benchmark_code,
            "as_of_date": as_of_date,
        },
    )
    row = result.fetchone()

    if not row or row.trading_days_count == 0:
        logger.warning("No sufficient return data found for 120d Beta calculation.")
        return None

    return AtomicPortfolioBeta120dRecord(
        fund_id=str(row.fund_id),
        benchmark_code=str(row.benchmark_code),
        window_start_date=row.window_start_date,
        window_end_date=row.window_end_date,
        trading_days_count=int(row.trading_days_count),
        avg_portfolio_return_pct=float(row.avg_portfolio_return_pct or 0.0),
        avg_benchmark_return_pct=float(row.avg_benchmark_return_pct or 0.0),
        var_benchmark=float(row.var_benchmark or 0.0),
        cov_portfolio_benchmark=float(row.cov_portfolio_benchmark or 0.0),
        beta_120d=float(row.beta_120d or 0.0),
        beta_regr_slope_120d=float(row.beta_regr_slope_120d or 0.0),
        r_squared_120d=float(row.r_squared_120d or 0.0),
    )