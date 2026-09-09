"""Authenticated proxy for the standalone professional risk-testing module."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.deps import CurrentUser, PortfolioViewer, ProcessingClient

router = APIRouter()


async def _proxy(client: ProcessingClient, method: str, path: str, **kwargs: Any) -> Any:
    response = await getattr(client, method)(path, **kwargs)
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/capabilities", summary="FinancePy 风险测试能力")
async def capabilities(_user: CurrentUser, client: ProcessingClient) -> Any:
    """Return engine/runtime capabilities to authenticated users."""

    return await _proxy(client, "get", "/risk-testing/capabilities")


@router.get("/catalog", summary="风险情景目录")
async def catalog(
    _user: CurrentUser,
    client: ProcessingClient,
    category: str | None = Query(default=None),
) -> Any:
    """Return built-in scenario definitions."""

    params = {"category": category} if category else {}
    return await _proxy(client, "get", "/risk-testing/catalog", params=params)


@router.get("/holdings/{fund_id}", summary="历史回测当前持仓及权重")
async def historical_backtest_holdings(
    fund_id: str,
    as_of_date: str,
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    """Return authorized current holdings for adjustable backtest weights."""

    return await _proxy(
        client,
        "get",
        f"/risk-testing/holdings/{fund_id}",
        params={"as_of_date": as_of_date},
        timeout=120.0,
    )


@router.post("/run/{fund_id}", summary="运行专业风险测试")
async def run_risk_test(
    fund_id: str,
    _user: PortfolioViewer,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    """Run an analytic after existing portfolio-level authorization."""

    return await _proxy(
        client,
        "post",
        f"/risk-testing/run/{fund_id}",
        json=payload,
        timeout=120.0,
    )


@router.post("/run-xml/{fund_id}", summary="使用 XML 配置运行专业风险测试")
async def run_risk_test_xml(
    fund_id: str,
    request: Request,
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    """Proxy XML configurations after existing portfolio authorization."""

    payload = await request.body()
    return await _proxy(
        client,
        "post",
        f"/risk-testing/run-xml/{fund_id}",
        content=payload,
        headers={"Content-Type": "application/xml"},
        timeout=120.0,
    )
