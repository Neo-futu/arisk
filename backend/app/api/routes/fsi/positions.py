"""FSI 持倉代理路由 — 轉發到 2_processing FastAPI（processing:8001）。"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import PortfolioViewer, ProcessingClient

router = APIRouter()


@router.get("/{fund_id}", summary="持倉列表")
async def get_positions(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="估值日期 YYYY-MM-DD")],
    _user: PortfolioViewer,
    client: ProcessingClient,
    asset_type: str | None = Query(default=None, description="資產類別過濾（bond/cd/deposit/repo...）"),
) -> Any:
    """查詢指定基金當日持倉（代理 processing /positions）。"""
    params: dict[str, Any] = {"as_of_date": str(as_of_date)}
    if asset_type:
        params["asset_type"] = asset_type
    resp = await client.get(f"/positions/{fund_id}", params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
