"""投資風險分析代理路由 — 計算由 2_processing 執行。"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, ProcessingClient

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


@router.get("/overview/{fund_id}", summary="組合概況")
async def get_portfolio_overview(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/overview/{fund_id}",
        {"as_of_date": str(as_of_date)},
    )


@router.get("/risk-indicators/{fund_id}", summary="投資風險指標")
async def get_risk_indicators(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/risk-indicators/{fund_id}",
        {"start": str(start), "end": str(end)},
    )


@router.get("/attribution/{fund_id}", summary="績效歸因")
async def get_performance_attribution(
    fund_id: str,
    start: Annotated[date, Query(description="區間開始日期")],
    end: Annotated[date, Query(description="區間結束日期")],
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        f"/investment/attribution/{fund_id}",
        {"start": str(start), "end": str(end)},
    )
