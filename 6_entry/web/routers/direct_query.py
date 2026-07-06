"""Direct Query Router — 直接調用 Processing API（低延遲，非 Agent）。"""
from __future__ import annotations

import os
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")

router = APIRouter()
_headers = {"X-API-Key": PROCESSING_API_KEY}


async def _get_client() -> httpx.AsyncClient:  # type: ignore[return]
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=_headers, timeout=30) as client:
        yield client


@router.get("/positions/{fund_id}")
async def query_positions(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    asset_type: str | None = None,
    client: httpx.AsyncClient = Depends(_get_client),
):
    """直接查詢持倉（低延遲）。"""
    params = {"as_of_date": str(as_of_date)}
    if asset_type:
        params["asset_type"] = asset_type
    resp = await client.get(f"/positions/{fund_id}", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/risk/exposure/{fund_id}")
async def query_exposure(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    client: httpx.AsyncClient = Depends(_get_client),
):
    """直接查詢風控暴露（低延遲）。"""
    resp = await client.get(f"/risk/exposure/{fund_id}", params={"as_of_date": str(as_of_date)})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/risk/var/{fund_id}")
async def query_var(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    confidence: float = 0.99,
    horizon_days: int = 1,
    method: str = "historical",
    client: httpx.AsyncClient = Depends(_get_client),
):
    """直接查詢 VaR（低延遲）。"""
    resp = await client.get(
        f"/risk/var/{fund_id}",
        params={
            "as_of_date": str(as_of_date),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "method": method,
        },
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/risk/var-compare/{fund_id}")
async def query_var_compare(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    confidence: float = 0.99,
    horizon_days: int = 1,
    simulations: int = 10000,
    client: httpx.AsyncClient = Depends(_get_client),
):
    """三方法 VaR 對比（historical / monte_carlo / distribution）。"""
    method_list = ("historical", "monte_carlo", "distribution")
    results = []

    for method in method_list:
        params = {
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

        payload = resp.json()
        payload["method_requested"] = method
        results.append(payload)

    max_var_pct_nav = max((float(r.get("var_pct_nav", 0.0) or 0.0) for r in results), default=0.0)
    return {
        "fund_id": fund_id,
        "as_of_date": str(as_of_date),
        "confidence": confidence,
        "horizon_days": horizon_days,
        "results": results,
        "max_var_pct_nav": max_var_pct_nav,
    }
