"""Authenticated portfolio-optimization proxy routes (analysis + chart PNG)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

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


@router.get("/universe")
async def universe(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/portfolio-opt/universe")


@router.get("/portfolios")
async def portfolios(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/portfolio-opt/portfolios")


@router.get("/holdings/{port_id}")
async def holdings(port_id: str, _user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", f"/portfolio-opt/holdings/{port_id}")


@router.get("/risk-free-options")
async def risk_free_options(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/portfolio-opt/risk-free-options")


@router.post("/evaluate")
async def evaluate(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/portfolio-opt/evaluate", json=payload)


@router.post("/analyze")
async def analyze(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/portfolio-opt/analyze", json=payload)


@router.post("/chart/{name}")
async def chart(
    name: str,
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Response:
    response = await client.post(f"/portfolio-opt/chart/{name}", json=payload)
    if response.status_code != 200:
        detail: Any = response.text
        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=response.status_code, detail=detail)
    return Response(
        content=response.content,
        media_type="image/png",
        headers={"Content-Disposition": response.headers.get("content-disposition", f'attachment; filename="{name}.png"')},
    )
