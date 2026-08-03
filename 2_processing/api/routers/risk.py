"""風控 API Router。"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key
from ...tools.risk.exposure_engine import compute_exposure, find_latest_exposure_date
from ...tools.risk.var_calculator import (
    compute_distribution_var,
    compute_historical_var,
    compute_monte_carlo_var,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/exposure-latest-date/{fund_id}")
async def get_exposure_latest_date(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="參考日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """返回基金在參考日期之前（含當天）的最新可用暴露數據日期。"""
    effective_date = await find_latest_exposure_date(fund_id=fund_id, as_of_date=as_of_date, db=db)
    return {
        "fund_id": fund_id,
        "requested_as_of_date": as_of_date,
        "effective_date": effective_date,
    }


@router.get("/exposure/{fund_id}")
async def get_exposure(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="持倉日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """計算基金指定日期的暴露指標及 MMF 合規狀態。"""
    result = await compute_exposure(fund_id, as_of_date, db)
    return {
        "fund_id": result.fund_id,
        "as_of_date": result.as_of_date,
        "total_nav_hkd": result.total_nav_hkd,
        "wam_days": result.wam_days,
        "wal_days": result.wal_days,
        "daily_liquid_pct": result.daily_liquid_pct,
        "weekly_liquid_pct": result.weekly_liquid_pct,
        "is_compliant": result.is_compliant,
        "breach_flags": list(result.breach_flags.keys()),
        "by_asset_type": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                          for k, v in result.by_asset_type.items()},
        "by_currency": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                        for k, v in result.by_currency.items()},
        "by_maturity_bucket": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                                for k, v in result.by_maturity_bucket.items()},
        "top_issuers": sorted(
            [{"issuer": k, "mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
             for k, v in result.by_issuer.items()],
            key=lambda x: x["pct"], reverse=True
        )[:10],
    }


@router.get("/var/{fund_id}")
async def get_var(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    confidence: float = 0.99,
    horizon_days: int = 1,
    method: str = "historical",
    simulations: int = 10000,
    db: AsyncSession = Depends(get_db),
):
    """計算基金 VaR。method: historical | monte_carlo | distribution。"""
    method_normalized = method.lower()
    if method_normalized == "historical":
        result = await compute_historical_var(fund_id, as_of_date, db, confidence, horizon_days)
    elif method_normalized in {"distribution", "parametric"}:
        result = await compute_distribution_var(fund_id, as_of_date, db, confidence, horizon_days)
    elif method_normalized in {"monte_carlo", "monte-carlo", "mc"}:
        result = await compute_monte_carlo_var(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
            confidence=confidence,
            horizon_days=horizon_days,
            simulations=simulations,
        )
    else:
        result = await compute_historical_var(fund_id, as_of_date, db, confidence, horizon_days)

    return {
        "fund_id": result.fund_id,
        "as_of_date": result.as_of_date,
        "confidence": result.confidence,
        "horizon_days": result.horizon_days,
        "var_hkd": result.var_amount_hkd,
        "var_pct_nav": result.var_pct_nav,
        "cvar_hkd": result.cvar_amount_hkd,
        "method": result.method,
        "sample_size": result.sample_size,
    }
