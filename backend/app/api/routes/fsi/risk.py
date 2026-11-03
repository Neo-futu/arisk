"""FSI 風控代理路由 — 轉發到 2_processing FastAPI（processing:8001）。

所有路由均需 JWT 認證（CurrentUser 依賴），保障只有登錄用戶才能訪問業務數據。
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.deps import CurrentUser, PortfolioViewer, ProcessingClient, SessionDep
from app.services.portfolio_access import list_accessible_portfolios

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


@router.get("/dashboard-overview", summary="当前用户全部有权组合风控概览")
async def get_dashboard_overview(
    as_of_date: Annotated[date, Query(description="参考日期 YYYY-MM-DD")],
    current_user: CurrentUser,
    session: SessionDep,
    client: ProcessingClient,
) -> dict[str, Any]:
    portfolios = list_accessible_portfolios(session, current_user)

    async def load_portfolio(portfolio: dict[str, object]) -> dict[str, Any]:
        fund_id = str(portfolio["port_id"])
        latest_response = await client.get(
            f"/risk/exposure-latest-date/{fund_id}",
            params={"as_of_date": str(as_of_date)},
        )
        if latest_response.status_code != 200:
            return {**portfolio, "status": "error", "error": latest_response.text}

        latest_payload = latest_response.json()
        effective_date = latest_payload.get("effective_date")
        if not effective_date:
            return {**portfolio, "status": "no_data", "effective_date": None}

        exposure_response = await client.get(
            f"/risk/exposure/{fund_id}",
            params={"as_of_date": effective_date},
        )
        if exposure_response.status_code != 200:
            return {
                **portfolio,
                "status": "error",
                "effective_date": effective_date,
                "error": exposure_response.text,
            }
        exposure = exposure_response.json()
        return {
            **portfolio,
            "status": "ok",
            "effective_date": effective_date,
            "total_nav_hkd": exposure.get("total_nav_hkd", 0),
            "wam_days": exposure.get("wam_days", 0),
            "wal_days": exposure.get("wal_days", 0),
            "is_compliant": exposure.get("is_compliant", False),
            "breach_count": len(exposure.get("breach_flags") or []),
            "breach_flags": exposure.get("breach_flags") or [],
        }

    items = await asyncio.gather(*(load_portfolio(item) for item in portfolios))
    ok_items = [item for item in items if item.get("status") == "ok"]
    return {
        "requested_as_of_date": str(as_of_date),
        "total": len(items),
        "with_data": len(ok_items),
        "compliant": sum(1 for item in ok_items if item.get("is_compliant")),
        "breached": sum(1 for item in ok_items if not item.get("is_compliant")),
        "portfolios": items,
    }


@router.get("/exposure/{fund_id}", summary="暴露分析 + SFC MMF 合規狀態")
async def get_exposure(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    """WAM / WAL / 流動性 / 集中度 / 合規狀態（代理 processing /risk/exposure）。"""
    return await _proxy(client, f"/risk/exposure/{fund_id}", {"as_of_date": str(as_of_date)})


@router.get("/exposure-latest-date/{fund_id}", summary="基金最新可用暴露數據日期")
async def get_exposure_latest_date(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="參考日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    """返回基金在參考日期之前（含當天）的最新可用暴露數據日期。"""
    return await _proxy(client, f"/risk/exposure-latest-date/{fund_id}", {"as_of_date": str(as_of_date)})


@router.get("/var/{fund_id}", summary="VaR 計算")
async def get_var(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    _user: PortfolioViewer,
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
    _user: PortfolioViewer,
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


async def _proxy_post(client: ProcessingClient, path: str, payload: dict[str, Any]) -> Any:
    response = await client.post(path, json=payload)
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/limits/catalog", summary="統一 Limit Engine / 風險治理目錄")
async def limits_catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy(client, "/risk/limits/catalog")


@router.get("/governance/catalog", summary="風險治理目錄")
async def governance_catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy(client, "/risk/governance/catalog")


@router.get("/governance/pack/{fund_id}", summary="風險治理工作台數據包")
async def governance_pack(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值/持倉日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
    lookback_days: Annotated[int, Query(ge=30, le=5000)] = 500,
) -> Any:
    return await _proxy(
        client,
        f"/risk/governance/pack/{fund_id}",
        {"as_of_date": str(as_of_date), "lookback_days": lookback_days},
    )


@router.post("/pre-trade", summary="前置風控")
async def pre_trade(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_post(client, "/risk/pre-trade", payload)
