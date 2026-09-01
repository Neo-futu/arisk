"""Authenticated indicator-explorer proxy routes (DataJungle-style)."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import CurrentUser, ProcessingClient, SessionDep
from app.models import User
from app.services.portfolio_access import ensure_global_permission

router = APIRouter()


def require_market_data_manager(
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_global_permission(session, current_user, "market_data.manage")
    return current_user


MarketDataManager = Annotated[User, Depends(require_market_data_manager)]


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


def _actor(user: User) -> str:
    return str(user.id)


@router.get("/catalog")
async def catalog(
    _user: CurrentUser,
    client: ProcessingClient,
    category: str | None = None,
    country: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/indicators/catalog",
        params={"category": category, "country": country},
    )


@router.get("/series")
async def series(
    indicator_ids: str,
    _user: CurrentUser,
    client: ProcessingClient,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/indicators/series",
        params={
            "indicator_ids": indicator_ids,
            "period": period,
            "start": start,
            "end": end,
        },
    )


@router.get("/series/export")
async def export_series(
    indicator_ids: str,
    _user: CurrentUser,
    client: ProcessingClient,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Response:
    response = await client.get(
        "/indicators/series/export",
        params={
            "indicator_ids": indicator_ids,
            "period": period,
            "start": start,
            "end": end,
        },
    )
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return Response(
        content=response.content,
        media_type="text/csv",
        headers={
            "Content-Disposition": response.headers.get(
                "content-disposition", 'attachment; filename="indicators.csv"'
            )
        },
    )


@router.post("/defs", status_code=201)
async def create_def(
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/indicators/defs",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.post("/{indicator_id}/observations", status_code=201)
async def upsert_observation(
    indicator_id: str,
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/indicators/{indicator_id}/observations",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/{indicator_id}/observations/{obs_date}")
async def update_observation(
    indicator_id: str,
    obs_date: date,
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/indicators/{indicator_id}/observations/{obs_date}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/{indicator_id}/observations/{obs_date}")
async def delete_observation(
    indicator_id: str,
    obs_date: date,
    current_user: MarketDataManager,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/indicators/{indicator_id}/observations/{obs_date}",
        params={"actor": _actor(current_user)},
    )
