"""Authenticated portfolio cockpit proxy routes (Module 2.1, read-only)."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, ProcessingClient, SessionDep
from app.services.portfolio_access import list_accessible_portfolios

router = APIRouter()


@router.get("/overview", summary="当前用户全部有权组合基本盘驾驶舱")
async def overview(
    current_user: CurrentUser,
    session: SessionDep,
    client: ProcessingClient,
    start_date: Annotated[date | None, Query(description="区间开始")] = None,
    end_date: Annotated[date | None, Query(description="区间结束；省略时回退 as_of_date")] = None,
    as_of_date: Annotated[date | None, Query(description="兼容旧参数，等同结束日期")] = None,
) -> Any:
    portfolios = list_accessible_portfolios(session, current_user)
    port_ids = ",".join(str(p["port_id"]) for p in portfolios)
    ended = end_date or as_of_date
    if not port_ids:
        return {
            "as_of_date": ended.isoformat() if ended else None,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": ended.isoformat() if ended else None,
            "summary": {
                "total_portfolios": 0,
                "with_data": 0,
                "mmf_count": 0,
                "breached": 0,
                "warned": 0,
                "by_type": {},
                "total_aum": {},
            },
            "portfolios": [],
        }

    params: dict[str, Any] = {"port_ids": port_ids}
    if start_date is not None:
        params["start_date"] = str(start_date)
    if ended is not None:
        params["end_date"] = str(ended)
        params["as_of_date"] = str(ended)
    response = await client.get("/portfolio-cockpit/overview", params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
