"""投資風險分析代理路由 — 計算由 2_processing 執行。"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import PortfolioTradeManager, PortfolioViewer, ProcessingClient

router = APIRouter()


async def _proxy(
    client: ProcessingClient,
    path: str,
    params: dict[str, Any],
) -> Any:
    response = await client.get(path, params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.get("/basic-info/{fund_id}", summary="基金基本信息與投資經理")
async def get_basic_info(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/basic-info/{fund_id}",
        {"as_of_date": str(as_of_date)},
    )


@router.get("/overview/{fund_id}", summary="組合概況")
async def get_portfolio_overview(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/overview/{fund_id}",
        {"as_of_date": str(as_of_date)},
    )


@router.get("/overview-timeseries/{fund_id}", summary="組合概況時序圖表")
async def get_portfolio_overview_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/overview-timeseries/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/risk-indicators/{fund_id}", summary="投資風險指標")
async def get_risk_indicators(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/risk-indicators/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/risk-indicators-timeseries/{fund_id}", summary="投資風險指標時序圖表")
async def get_risk_indicator_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/risk-indicators-timeseries/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/attribution/{fund_id}", summary="績效歸因")
async def get_performance_attribution(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/attribution/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/attribution-timeseries/{fund_id}", summary="績效歸因時序圖表")
async def get_performance_attribution_timeseries(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/attribution-timeseries/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/rates-credit/{fund_id}", summary="利率與信用風險敏感度")
async def get_rates_credit(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/rates-credit/{fund_id}",
        {"as_of_date": str(as_of_date)},
    )


@router.get("/liquidity-stress/{fund_id}", summary="流動性風險與壓力測試")
async def get_liquidity_stress(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
    redemption_pct: Annotated[float, Query(description="贖回比例（%）", ge=1, le=80)] = 20,
    rate_shock_bps: Annotated[float, Query(description="利率衝擊（bps）", ge=1, le=1000)] = 50,
) -> Any:
    return await _proxy(
        client,
        f"/investment/liquidity-stress/{fund_id}",
        {
            "as_of_date": str(as_of_date),
            "redemption_pct": redemption_pct,
            "rate_shock_bps": rate_shock_bps,
        },
    )


@router.get("/pretrade-check/{fund_id}", summary="風險預算與前置試算")
async def get_pretrade_check(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    trade_amount: Annotated[float, Query(description="交易金額", gt=0)],
    _user: PortfolioTradeManager,
    client: ProcessingClient,
    trade_side: Annotated[str, Query(description="BUY 或 SELL")] = "BUY",
    asset_class: Annotated[str, Query(description="資產類別")] = "BOND_CORP",
    duration_years: Annotated[float, Query(description="交易資產久期（年）", ge=0, le=30)] = 2,
    issuer_name: Annotated[str, Query(description="發行人")] = "UNKNOWN_ISSUER",
) -> Any:
    return await _proxy(
        client,
        f"/investment/pretrade-check/{fund_id}",
        {
            "as_of_date": str(as_of_date),
            "trade_amount": trade_amount,
            "trade_side": trade_side,
            "asset_class": asset_class,
            "duration_years": duration_years,
            "issuer_name": issuer_name,
        },
    )


@router.get("/macro-dynamics/{fund_id}", summary="宏觀與市場動態風險")
async def get_macro_dynamics(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/macro-dynamics/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/factor-behavior/{fund_id}", summary="基本面、因子與行為風險")
async def get_factor_behavior(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/factor-behavior/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/kpi-catalog", summary="投資風險 KPI 目錄")
async def get_kpi_catalog(
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(client, "/investment/kpi-catalog", {})


@router.get("/kpis/{fund_id}", summary="投資風險統一 KPI 包")
async def get_kpi_pack(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
    confidence: Annotated[float, Query(description="VaR/CVaR/ES 置信度", gt=0.5, lt=1.0)] = 0.99,
    lookback_days: Annotated[int, Query(ge=30, le=5000)] = 500,
) -> Any:
    return await _proxy(
        client,
        f"/investment/kpis/{fund_id}",
        {
            "as_of_date": str(as_of_date),
            "confidence": confidence,
            "lookback_days": lookback_days,
        },
    )
