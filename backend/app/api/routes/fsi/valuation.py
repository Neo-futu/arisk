"""Authenticated valuation & P&L proxy routes (Module 4, read-only)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import PortfolioViewer, ProcessingClient

router = APIRouter()


async def _proxy(client: ProcessingClient, method: str, path: str, **kwargs: Any) -> Any:
    response = await getattr(client, method)(path, **kwargs)
    if response.status_code not in (200, 201):
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/report/{fund_id}")
async def valuation_report(
    fund_id: str,
    as_of_date: date,
    _user: PortfolioViewer,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/valuation/report/{fund_id}",
        params={"as_of_date": as_of_date},
    )


@router.get("/pnl/{fund_id}")
async def pnl_analysis(
    fund_id: str,
    _user: PortfolioViewer,
    client: ProcessingClient,
    start: date | None = None,
    end: date | None = None,
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/valuation/pnl/{fund_id}",
        params={"start": start, "end": end},
    )
