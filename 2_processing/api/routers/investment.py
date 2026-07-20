"""投資風險分析 API Router。"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...tools.performance.investment_analysis import (
    compute_performance_attribution,
    compute_portfolio_overview,
    compute_risk_indicators,
)
from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/overview/{fund_id}")
async def get_portfolio_overview(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """組合概況：總體業績、資產配置、前十大個股及股票行業配置。"""
    return await compute_portfolio_overview(fund_id, as_of_date, db)


@router.get("/risk-indicators/{fund_id}")
async def get_risk_indicators(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """區間收益率、波動率、最大回撤、股票換手率及股票 Beta。"""
    _validate_period(start, end)
    return await compute_risk_indicators(fund_id, start, end, db)


@router.get("/attribution/{fund_id}")
async def get_performance_attribution(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """收益貢獻、行業歸因/超配、個股損益排名及日均十大重倉。"""
    _validate_period(start, end)
    return await compute_performance_attribution(fund_id, start, end, db)


def _validate_period(start: date, end: date) -> None:
    if start > end:
        raise HTTPException(status_code=422, detail="start 不得晚於 end")
    if (end - start).days > 3660:
        raise HTTPException(status_code=422, detail="查詢區間不得超過 10 年")
