"""VaR 計算器：歷史法、蒙地卡羅法、分佈公式法。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Tuple

import numpy as np
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
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


async def _load_nav_returns(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    lookback_days: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """讀取 NAV 並返回（navs, daily_returns）。

    優先使用 fsi.balance_portfolio_nav；若不存在/無數據再回退。
    """
    start_date = as_of_date - timedelta(days=lookback_days * 2)
    nav_records = []

    # 1) 首選：估值層組合 NAV（本專案當前主要來源）
    try:
        rows = await db.execute(
            text("""
                SELECT evaluate_date AS nav_date,
                       COALESCE(net_asset, total_asset) AS total_nav
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fid
                  AND evaluate_date BETWEEN :start AND :end
                  AND COALESCE(net_asset, total_asset) IS NOT NULL
                ORDER BY evaluate_date
            """),
            {"fid": fund_id, "start": start_date, "end": as_of_date},
        )
        nav_records = rows.fetchall()
    except SQLAlchemyError as exc:
        logger.info("balance_portfolio_nav unavailable, fallback to nav_history/raw_nav: fund_id=%s, err=%s", fund_id, exc)
        await db.rollback()

    # 2) 次選：標準化 NAV 歷史表
    if not nav_records:
        try:
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
        except SQLAlchemyError as exc:
            logger.info("nav_history unavailable, fallback to raw_nav: fund_id=%s, err=%s", fund_id, exc)
            await db.rollback()

    # 3) 回退：raw NAV（fund_code / port_no）
    if not nav_records:
        try:
            rows = await db.execute(
                text("""
                    SELECT nav_date, total_nav
                    FROM fsi.raw_nav
                    WHERE nav_date BETWEEN :start AND :end
                      AND total_nav IS NOT NULL
                      AND (
                            fund_code = :fid
                         OR port_no = :fid
                         OR COALESCE(fund_code, '') = :fid
                         OR COALESCE(port_no, '') = :fid
                      )
                    ORDER BY nav_date
                """),
                {"fid": fund_id, "start": start_date, "end": as_of_date},
            )
            nav_records = rows.fetchall()
        except SQLAlchemyError as exc:
            logger.warning("raw_nav query failed for VaR: fund_id=%s, err=%s", fund_id, exc)
            await db.rollback()
            return np.array([]), np.array([])

    if len(nav_records) < 2:
        return np.array([]), np.array([])

    navs = np.array([float(r.total_nav) for r in nav_records], dtype=float)
    daily_returns = np.diff(navs) / navs[:-1]
    daily_returns = daily_returns[-lookback_days:]
    return navs, daily_returns


def _insufficient_data_result(
    fund_id: str,
    as_of_date: date,
    confidence: float,
    horizon_days: int,
) -> VaRResult:
    return VaRResult(
        fund_id=fund_id,
        as_of_date=as_of_date,
        confidence=confidence,
        horizon_days=horizon_days,
        var_amount_hkd=0,
        var_pct_nav=0,
        cvar_amount_hkd=0,
        method="INSUFFICIENT_DATA",
        sample_size=0,
    )


async def compute_historical_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
    min_observations: int = 30,
) -> VaRResult:
    """歷史模擬法 VaR：使用過去 252（預設）交易日收益率。"""
    navs, daily_returns = await _load_nav_returns(fund_id, as_of_date, db, lookback_days)
    if daily_returns.size < min_observations or navs.size < 2:
        logger.warning("Insufficient NAV data for historical VaR: fund_id=%s", fund_id)
        return _insufficient_data_result(fund_id, as_of_date, confidence, horizon_days)

    horizon_returns = daily_returns * np.sqrt(horizon_days)
    alpha = 1 - confidence
    var_pct = float(np.percentile(horizon_returns, alpha * 100))
    tail = horizon_returns[horizon_returns <= var_pct]
    cvar_pct = float(np.mean(tail)) if tail.size > 0 else var_pct

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


async def compute_distribution_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
    min_observations: int = 30,
) -> VaRResult:
    """分佈公式法 VaR：假設日收益率服從正態分佈。"""
    from scipy.stats import norm

    navs, daily_returns = await _load_nav_returns(fund_id, as_of_date, db, lookback_days)
    if daily_returns.size < min_observations or navs.size < 2:
        logger.warning("Insufficient NAV data for distribution VaR: fund_id=%s", fund_id)
        return _insufficient_data_result(fund_id, as_of_date, confidence, horizon_days)

    mu = float(np.mean(daily_returns))
    sigma = float(np.std(daily_returns, ddof=1))
    if sigma <= 0:
        logger.warning("Zero volatility in NAV returns for fund_id=%s", fund_id)
        return _insufficient_data_result(fund_id, as_of_date, confidence, horizon_days)

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
        method="DISTRIBUTION_FORMULA",
        sample_size=len(daily_returns),
    )


async def compute_parametric_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
    min_observations: int = 30,
) -> VaRResult:
    """向後兼容別名：參數法 = 分佈公式法。"""
    return await compute_distribution_var(
        fund_id=fund_id,
        as_of_date=as_of_date,
        db=db,
        confidence=confidence,
        horizon_days=horizon_days,
        lookback_days=lookback_days,
        min_observations=min_observations,
    )


async def compute_monte_carlo_var(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
    min_observations: int = 30,
    simulations: int = 10000,
    random_seed: int | None = 42,
) -> VaRResult:
    """蒙地卡羅 VaR：用歷史樣本估計 μ/σ，再模擬收益率分佈。"""
    navs, daily_returns = await _load_nav_returns(fund_id, as_of_date, db, lookback_days)
    if daily_returns.size < min_observations or navs.size < 2:
        logger.warning("Insufficient NAV data for Monte Carlo VaR: fund_id=%s", fund_id)
        return _insufficient_data_result(fund_id, as_of_date, confidence, horizon_days)

    mu = float(np.mean(daily_returns))
    sigma = float(np.std(daily_returns, ddof=1))
    if sigma <= 0:
        logger.warning("Zero volatility in NAV returns for fund_id=%s", fund_id)
        return _insufficient_data_result(fund_id, as_of_date, confidence, horizon_days)

    rng = np.random.default_rng(random_seed)
    horizon_mu = mu * horizon_days
    horizon_sigma = sigma * np.sqrt(horizon_days)
    simulated_returns = rng.normal(horizon_mu, horizon_sigma, int(simulations))

    alpha = 1 - confidence
    var_pct = float(np.percentile(simulated_returns, alpha * 100))
    tail = simulated_returns[simulated_returns <= var_pct]
    cvar_pct = float(np.mean(tail)) if tail.size > 0 else var_pct

    current_nav = float(navs[-1])
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
        method="MONTE_CARLO",
        sample_size=int(simulations),
    )
