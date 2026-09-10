"""Authenticated portfolio-optimization proxy routes (analysis + chart PNG)."""
from __future__ import annotations

from typing import Any

from datetime import date

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


@router.get("/market-quotes/history/{security_code}")
async def market_quote_history(
    security_code: str,
    _user: CurrentUser,
    client: ProcessingClient,
    start: date,
    end: date,
    price_type: str = "CLOSE",
    data_source: str = "db",
) -> Any:
    return await _proxy_json(
        client,
        "get",
        f"/portfolio-opt/market-quotes/history/{security_code}",
        params={"start": start, "end": end, "price_type": price_type, "data_source": data_source},
    )


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


@router.get("/catalog")
async def catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", "/portfolio-opt/catalog")


@router.post("/governed-optimize")
async def governed_optimize(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/portfolio-opt/governed-optimize", json=payload)


@router.post("/simulate/clone")
async def simulate_clone(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/portfolio-opt/simulate/clone", json=payload)


@router.post("/simulate/{sim_id}/modify")
async def simulate_modify(
    sim_id: str,
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", f"/portfolio-opt/simulate/{sim_id}/modify", json=payload)


@router.post("/simulate/{sim_id}/optimize")
async def simulate_optimize(
    sim_id: str,
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", f"/portfolio-opt/simulate/{sim_id}/optimize", json=payload)


@router.post("/simulate/{sim_id}/stress")
async def simulate_stress(
    sim_id: str,
    _user: CurrentUser,
    client: ProcessingClient,
    scenario_id: str = "gfc_2008",
) -> Any:
    return await _proxy_json(
        client,
        "post",
        f"/portfolio-opt/simulate/{sim_id}/stress",
        params={"scenario_id": scenario_id},
    )


@router.get("/simulate/{sim_id}/compare")
async def simulate_compare(sim_id: str, _user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy_json(client, "get", f"/portfolio-opt/simulate/{sim_id}/compare")


@router.post("/live/apply")
async def live_apply(
    _user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy_json(client, "post", "/portfolio-opt/live/apply", json=payload)
