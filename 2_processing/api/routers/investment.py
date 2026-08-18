"""投資風險分析 API Router。"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...tools.performance.investment_analysis import (
    compute_factor_behavior_risk,
    compute_liquidity_stress_testing,
    compute_macro_market_dynamics,
    compute_performance_attribution,
    compute_performance_attribution_timeseries,
    compute_portfolio_basic_info,
    compute_portfolio_overview,
    compute_portfolio_overview_timeseries,
    compute_pretrade_risk_budget,
    compute_rates_credit_sensitivity,
    compute_risk_indicator_timeseries,
    compute_risk_indicators,
)
from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/basic-info/{fund_id}")
async def get_portfolio_basic_info(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """基金基本信息：主數據、資金類型、最近數據日與投資經理任職記錄。"""
    return await compute_portfolio_basic_info(fund_id, as_of_date, db)


@router.get("/overview/{fund_id}")
async def get_portfolio_overview(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """組合概況：總體業績、資產配置、前十大個股及股票行業配置。"""
    return await compute_portfolio_overview(fund_id, as_of_date, db)


@router.get("/overview-timeseries/{fund_id}")
async def get_portfolio_overview_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """組合概況圖表時序：NAV、淨資產與區間累積收益。"""
    _validate_period(start, end)
    return await compute_portfolio_overview_timeseries(fund_id, start, end, db)


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


@router.get("/risk-indicators-timeseries/{fund_id}")
async def get_risk_indicator_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """風險指標圖表時序：日收益、滾動波動、回撤與滾動 VaR。"""
    _validate_period(start, end)
    return await compute_risk_indicator_timeseries(fund_id, start, end, db)


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


@router.get("/attribution-timeseries/{fund_id}")
async def get_performance_attribution_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """績效歸因圖表時序：基金/基準/超額收益與日度損益貢獻。"""
    _validate_period(start, end)
    return await compute_performance_attribution_timeseries(fund_id, start, end, db)


def _validate_period(start: date, end: date) -> None:
    if start > end:
        raise HTTPException(status_code=422, detail="start 不得晚於 end")
    if (end - start).days > 3660:
        raise HTTPException(status_code=422, detail="查詢區間不得超過 10 年")


@router.get("/rates-credit/{fund_id}")
async def get_rates_credit_sensitivity(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """利率與信用風險敏感度：KRD/CS01/集中度/評級分佈。"""
    return await compute_rates_credit_sensitivity(fund_id, as_of_date, db)


@router.get("/liquidity-stress/{fund_id}")
async def get_liquidity_stress(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    redemption_pct: Annotated[float, Query(description="贖回比例（%）", ge=1, le=80)] = 20,
    rate_shock_bps: Annotated[float, Query(description="利率衝擊（bps）", ge=1, le=1000)] = 50,
    db: AsyncSession = Depends(get_db),
):
    """流動性階梯 + 壓力測試（歷史、贖回、利率衝擊）。"""
    return await compute_liquidity_stress_testing(
        fund_id=fund_id,
        as_of_date=as_of_date,
        redemption_pct=redemption_pct,
        rate_shock_bps=rate_shock_bps,
        db=db,
    )


@router.get("/pretrade-check/{fund_id}")
async def get_pretrade_check(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    trade_amount: Annotated[float, Query(description="交易金額（本位幣）", gt=0)],
    trade_side: Annotated[str, Query(description="BUY 或 SELL")] = "BUY",
    asset_class: Annotated[str, Query(description="資產類型，如 BOND_CORP")]= "BOND_CORP",
    duration_years: Annotated[float, Query(description="假設交易資產久期（年）", ge=0, le=30)] = 2.0,
    issuer_name: Annotated[str, Query(description="發行人名稱")] = "UNKNOWN_ISSUER",
    db: AsyncSession = Depends(get_db),
):
    """風險預算與前置試算：久期、集中度、交易衝擊。"""
    side = trade_side.upper()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=422, detail="trade_side 僅支持 BUY 或 SELL")
    return await compute_pretrade_risk_budget(
        fund_id=fund_id,
        as_of_date=as_of_date,
        trade_amount=trade_amount,
        trade_side=side,
        asset_class=asset_class,
        duration_years=duration_years,
        issuer_name=issuer_name,
        db=db,
    )


@router.get("/macro-dynamics/{fund_id}")
async def get_macro_dynamics(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """宏觀與市場動態風險：波動 regime、跨資產關聯、傳染風險。"""
    _validate_period(start, end)
    return await compute_macro_market_dynamics(fund_id, start, end, db)


@router.get("/factor-behavior/{fund_id}")
async def get_factor_behavior(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期 YYYY-MM-DD")],
    end: Annotated[date, Query(description="區間結束日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """基本面/因子/行為風險：風格暴露、擁擠度、集中度與踩踏預警。"""
    _validate_period(start, end)
    return await compute_factor_behavior_risk(fund_id, start, end, db)
