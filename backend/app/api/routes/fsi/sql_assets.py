"""Authenticated SQL asset library proxy routes (read-only)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, ProcessingClient

router = APIRouter()


async def _proxy(client: ProcessingClient, path: str, **kwargs: Any) -> Any:
    response = await client.get(path, **kwargs)
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/catalog")
async def catalog(
    _user: CurrentUser,
    client: ProcessingClient,
    group: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "/sql-assets/catalog",
        params={"group": group, "category": category, "search": search},
    )


@router.get("/asset")
async def asset(id: str, _user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy(client, "/sql-assets/asset", params={"id": id})


@router.get("/context")
async def context(
    _user: CurrentUser,
    client: ProcessingClient,
    group: str | None = None,
    category: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "/sql-assets/context",
        params={"group": group, "category": category},
    )
