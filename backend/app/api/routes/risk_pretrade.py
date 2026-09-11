"""Wave 6 public pre-trade path: POST /api/v1/risk/pre-trade."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.api.deps import CurrentUser, ProcessingClient

router = APIRouter()


async def _proxy_json(client: ProcessingClient, method: str, path: str, **kwargs: Any) -> Any:
    response = await getattr(client, method)(path, **kwargs)
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/limits/catalog")
async def limits_catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/risk/limits/catalog")


@router.post("/pre-trade")
async def pre_trade(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/risk/pre-trade", json=payload)
