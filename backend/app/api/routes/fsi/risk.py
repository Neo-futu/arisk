"""FSI 風控代理路由 — 轉發到 2_processing FastAPI（processing:8001）。

所有路由均需 JWT 認證（CurrentUser 依賴），保障只有登錄用戶才能訪問業務數據。
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import CurrentUser, ProcessingClient

router = APIRouter()


async def _proxy(
    client: ProcessingClient,
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """通用代理函數：GET 請求轉發到 processing，錯誤透傳。"""
    resp = await client.get(path, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/exposure/{fund_id}", summary="暴露分析 + SFC MMF 合規狀態")
async def get_exposure(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    """WAM / WAL / 流動性 / 集中度 / 合規狀態（代理 processing /risk/exposure）。"""
    return await _proxy(client, f"/risk/exposure/{fund_id}", {"as_of_date": str(as_of_date)})


@router.get("/exposure-latest-date/{fund_id}", summary="基金最新可用暴露數據日期")
async def get_exposure_latest_date(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="參考日期 YYYY-MM-DD")],
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    """返回基金在參考日期之前（含當天）的最新可用暴露數據日期。"""
    return await _proxy(client, f"/risk/exposure-latest-date/{fund_id}", {"as_of_date": str(as_of_date)})


@router.get("/var/{fund_id}", summary="VaR 計算")
async def get_var(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    _user: CurrentUser,
    client: ProcessingClient,
    confidence: float = 0.99,
    horizon_days: int = 1,
    method: str = "historical",
    simulations: int = 10000,
) -> Any:
    """VaR / CVaR（method: historical | monte_carlo | distribution）。"""
    return await _proxy(
        client,
        f"/risk/var/{fund_id}",
        {
            "as_of_date": str(as_of_date),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "method": method,
            "simulations": simulations,
        },
    )


@router.get("/var-compare/{fund_id}", summary="三方法 VaR 對比")
async def get_var_compare(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    _user: CurrentUser,
    client: ProcessingClient,
    confidence: float = 0.99,
    horizon_days: int = 1,
    simulations: int = 10000,
) -> Any:
    """並發執行三方法 VaR，返回匯總對比（historical / monte_carlo / distribution）。"""
    import asyncio

    async def _fetch_method(method: str) -> dict:
        params: dict[str, Any] = {
            "as_of_date": str(as_of_date),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "method": method,
        }
        if method == "monte_carlo":
            params["simulations"] = simulations
        resp = await client.get(f"/risk/var/{fund_id}", params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        data = resp.json()
        data["method_requested"] = method
        return data

    results = await asyncio.gather(
        _fetch_method("historical"),
        _fetch_method("monte_carlo"),
        _fetch_method("distribution"),
    )
    max_var_pct = max(float(r.get("var_pct_nav") or 0) for r in results)
    return {
        "fund_id": fund_id,
        "as_of_date": str(as_of_date),
        "confidence": confidence,
        "horizon_days": horizon_days,
        "results": list(results),
        "max_var_pct_nav": max_var_pct,
    }
