"""Authenticated data-management workbench proxy routes."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.api.deps import (
    CurrentUser,
    PortfolioManager,
    PortfolioTradeManager,
    PortfolioViewer,
    ProcessingClient,
    SessionDep,
)
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


def require_portfolio_admin(
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_global_permission(session, current_user, "portfolio.admin")
    return current_user


PortfolioAdmin = Annotated[User, Depends(require_portfolio_admin)]


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


@router.get("/positions/{fund_id}")
async def list_positions(
    fund_id: str,
    as_of_date: date,
    _user: PortfolioViewer,
    client: ProcessingClient,
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/data-management/positions/{fund_id}",
        params={"as_of_date": as_of_date, "search": search, "limit": limit},
    )


@router.post("/positions/{fund_id}", status_code=201)
async def create_position(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/positions/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/positions/{fund_id}/{subject_code}")
async def update_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    current_user: PortfolioManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/positions/{fund_id}/{subject_code}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/positions/{fund_id}/{subject_code}")
async def delete_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    current_user: PortfolioManager,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/positions/{fund_id}/{subject_code}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
    )


@router.get("/market-quotes")
async def list_market_quotes(
    price_date: date,
    _user: CurrentUser,
    client: ProcessingClient,
    search: str | None = None,
    market_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> Any:
    return await _proxy(
        client,
        "get",
        "/data-management/market-quotes",
        params={
            "price_date": price_date,
            "search": search,
            "market_id": market_id,
            "limit": limit,
        },
    )


@router.get("/market-quotes/history/{security_code}")
async def market_quote_history(
    security_code: str,
    start: date,
    end: date,
    _user: CurrentUser,
    client: ProcessingClient,
    price_type: str = "CLOSE",
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/data-management/market-quotes/history/{security_code}",
        params={"start": start, "end": end, "price_type": price_type},
    )


@router.post("/market-quotes", status_code=201)
async def create_market_quote(
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/data-management/market-quotes",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/market-quotes/{price_date}/{security_code}/{price_type}")
async def update_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/market-quotes/{price_date}/{security_code}/{price_type}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/market-quotes/{price_date}/{security_code}/{price_type}")
async def delete_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    current_user: MarketDataManager,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/market-quotes/{price_date}/{security_code}/{price_type}",
        params={"actor": _actor(current_user)},
    )


@router.get("/simulated-orders/{fund_id}")
async def list_simulated_orders(
    fund_id: str,
    _user: PortfolioViewer,
    client: ProcessingClient,
    as_of_date: date | None = None,
    include_cancelled: bool = False,
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/data-management/simulated-orders/{fund_id}",
        params={
            "as_of_date": as_of_date,
            "include_cancelled": include_cancelled,
        },
    )


@router.post("/simulated-orders/{fund_id}", status_code=201)
async def create_simulated_order(
    fund_id: str,
    current_user: PortfolioTradeManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/simulated-orders/{fund_id}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/simulated-orders/{fund_id}/{order_id}")
async def update_simulated_order(
    fund_id: str,
    order_id: UUID,
    current_user: PortfolioTradeManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/simulated-orders/{fund_id}/{order_id}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.post("/simulated-orders/{fund_id}/{order_id}/validate")
async def validate_simulated_order(
    fund_id: str,
    order_id: UUID,
    current_user: PortfolioTradeManager,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/simulated-orders/{fund_id}/{order_id}/validate",
        params={"actor": _actor(current_user)},
    )


@router.delete("/simulated-orders/{fund_id}/{order_id}")
async def cancel_simulated_order(
    fund_id: str,
    order_id: UUID,
    current_user: PortfolioTradeManager,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/simulated-orders/{fund_id}/{order_id}",
        params={"actor": _actor(current_user)},
    )


@router.get("/portfolios")
async def list_portfolios(
    _user: CurrentUser,
    client: ProcessingClient,
    search: str | None = None,
    include_inactive: bool = True,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/data-management/portfolios",
        params={"search": search, "include_inactive": include_inactive},
    )


@router.post("/portfolios", status_code=201)
async def create_portfolio(
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/data-management/portfolios",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/portfolios/{port_id}")
async def update_portfolio(
    port_id: str,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/portfolios/{port_id}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/portfolios/{port_id}")
async def delete_portfolio(
    port_id: str,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/portfolios/{port_id}",
        params={"actor": _actor(current_user)},
    )
