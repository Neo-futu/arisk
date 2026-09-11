"""Authenticated Agent kernel proxy: /api/v1/agents (JWT). Existing chat stays at /api/v1/fsi/agent."""
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


@router.get("/catalog")
async def catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/agents/catalog")


@router.post("/invoke")
async def invoke(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    return await _proxy_json(client, "post", "/agents/invoke", json=payload)
