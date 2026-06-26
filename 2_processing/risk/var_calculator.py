"""VaR 計算器：Historical Simulation + Parametric 兩種方法。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    fund_id: str
    as_of_date: date
    confidence: float
    horizon_days: int
    var_amount_hkd: float
    var_pct_nav: float
    cvar_amount_hkd: float
    method: str
    sample_size: int


async def compute_historical_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
) -> VaRResult:
    """歷史模擬法 VaR：使用過去 lookback_days 天的日收益率。"""
    start_date = as_of_date - timedelta(days=lookback_days * 2)

    # 取基金每日 NAV
    rows = await db.execute(
        text("""
            SELECT nav_date, total_nav
            FROM fsi.nav_history
            WHERE fund_id = :fid
              AND nav_date BETWEEN :start AND :end
            ORDER BY nav_date
        """),
        {"fid": fund_id, "start": start_date, "end": as_of_date},
    )
    nav_records = rows.fetchall()

    if len(nav_records) < 30:
        logger.warning("Insufficient NAV data for VaR: %d records", len(nav_records))
        return VaRResult(fund_id, as_of_date, confidence, horizon_days, 0, 0, 0, "INSUFFICIENT_DATA", 0)

    navs = np.array([float(r.total_nav) for r in nav_records])
    daily_returns = np.diff(navs) / navs[:-1]

    # 限制 lookback 窗口
    daily_returns = daily_returns[-lookback_days:]

    # Historical VaR
    horizon_returns = daily_returns * np.sqrt(horizon_days)
    alpha = 1 - confidence
    var_pct = float(np.percentile(horizon_returns, alpha * 100))
    cvar_pct = float(np.mean(horizon_returns[horizon_returns <= var_pct]))

    current_nav = navs[-1]
    var_hkd = abs(var_pct * current_nav)
    cvar_hkd = abs(cvar_pct * current_nav)

    return VaRResult(
        fund_id=fund_id,
        as_of_date=as_of_date,
        confidence=confidence,
        horizon_days=horizon_days,
        var_amount_hkd=var_hkd,
        var_pct_nav=abs(var_pct) * 100,
        cvar_amount_hkd=cvar_hkd,
        method="HISTORICAL_SIMULATION",
        sample_size=len(daily_returns),
    )


async def compute_parametric_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
) -> VaRResult:
    """參數法 VaR：假設正態分佈。"""
    from scipy.stats import norm

    start_date = as_of_date - timedelta(days=lookback_days * 2)
    rows = await db.execute(
        text("""
            SELECT nav_date, total_nav
            FROM fsi.nav_history
            WHERE fund_id = :fid
              AND nav_date BETWEEN :start AND :end
            ORDER BY nav_date
        """),
        {"fid": fund_id, "start": start_date, "end": as_of_date},
    )
    nav_records = rows.fetchall()

    if len(nav_records) < 30:
        return VaRResult(fund_id, as_of_date, confidence, horizon_days, 0, 0, 0, "INSUFFICIENT_DATA", 0)

    navs = np.array([float(r.total_nav) for r in nav_records])
    daily_returns = np.diff(navs) / navs[:-1]
    daily_returns = daily_returns[-lookback_days:]

    mu = float(np.mean(daily_returns))
    sigma = float(np.std(daily_returns, ddof=1))

    z_score = norm.ppf(1 - confidence)
    var_pct = -(mu * horizon_days + z_score * sigma * np.sqrt(horizon_days))
    cvar_pct = -(mu * horizon_days - sigma * np.sqrt(horizon_days) * norm.pdf(z_score) / (1 - confidence))

    current_nav = navs[-1]
    return VaRResult(
        fund_id=fund_id,
        as_of_date=as_of_date,
        confidence=confidence,
        horizon_days=horizon_days,
        var_amount_hkd=float(var_pct * current_nav),
        var_pct_nav=float(var_pct) * 100,
        cvar_amount_hkd=float(cvar_pct * current_nav),
        method="PARAMETRIC",
        sample_size=len(daily_returns),
    )
