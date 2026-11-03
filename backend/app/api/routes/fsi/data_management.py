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


@router.get("/catalog", summary="数据管理可维护表目录")
async def catalog(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy(client, "get", "/data-management/catalog")


@router.get("/availability", summary="持仓/行情最近可用日")
async def availability(
    _user: CurrentUser,
    client: ProcessingClient,
    fund_id: str | None = None,
    as_of_date: date | None = None,
) -> Any:
    params: dict[str, Any] = {}
    if fund_id:
        params["fund_id"] = fund_id
    if as_of_date:
        params["as_of_date"] = as_of_date.isoformat()
    return await _proxy(client, "get", "/data-management/availability", params=params)


@router.get("/positions/{fund_id}")
async def list_positions(
    fund_id: str,
    as_of_date: date,
    _user: PortfolioViewer,
    client: ProcessingClient,
    search: str | None = None,
    table: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    fallback: bool = True,
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/data-management/positions/{fund_id}",
        params={
            "as_of_date": as_of_date,
            "search": search,
            "table": table,
            "limit": limit,
            "fallback": fallback,
        },
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
    asset_class: str | None = None,
) -> Any:
    params: dict[str, Any] = {"as_of_date": as_of_date, "actor": _actor(current_user)}
    if asset_class:
        params["asset_class"] = asset_class
    return await _proxy(
        client,
        "patch",
        f"/data-management/positions/{fund_id}/{subject_code}",
        params=params,
        json=payload,
    )


@router.delete("/positions/{fund_id}/{subject_code}")
async def delete_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    current_user: PortfolioManager,
    client: ProcessingClient,
    asset_class: str | None = None,
) -> Any:
    params: dict[str, Any] = {"as_of_date": as_of_date, "actor": _actor(current_user)}
    if asset_class:
        params["asset_class"] = asset_class
    return await _proxy(
        client,
        "delete",
        f"/data-management/positions/{fund_id}/{subject_code}",
        params=params,
    )


@router.get("/market-quotes")
async def list_market_quotes(
    price_date: date,
    _user: CurrentUser,
    client: ProcessingClient,
    search: str | None = None,
    market_id: str | None = None,
    table: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    fallback: bool = True,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/data-management/market-quotes",
        params={
            "price_date": price_date,
            "search": search,
            "market_id": market_id,
            "table": table,
            "limit": limit,
            "fallback": fallback,
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
    table: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "get",
        f"/data-management/market-quotes/history/{security_code}",
        params={"start": start, "end": end, "price_type": price_type, "table": table},
    )


@router.post("/market-quotes", status_code=201)
async def create_market_quote(
    current_user: MarketDataManager,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
    table: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "post",
        "/data-management/market-quotes",
        params={"actor": _actor(current_user), "table": table},
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
    table: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/market-quotes/{price_date}/{security_code}/{price_type}",
        params={"actor": _actor(current_user), "table": table},
        json=payload,
    )


@router.delete("/market-quotes/{price_date}/{security_code}/{price_type}")
async def delete_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    current_user: MarketDataManager,
    client: ProcessingClient,
    table: str | None = None,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/market-quotes/{price_date}/{security_code}/{price_type}",
        params={"actor": _actor(current_user), "table": table},
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
    table: str | None = None,
    fund_id: str | None = None,
    as_of_date: date | None = None,
    fallback: bool = True,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/data-management/portfolios",
        params={
            "search": search,
            "include_inactive": include_inactive,
            "table": table,
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "fallback": fallback,
        },
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


@router.post("/share-classes", status_code=201)
async def create_share_class(
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/data-management/share-classes",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/share-classes/{class_id}")
async def update_share_class(
    class_id: str,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/share-classes/{class_id}",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/share-classes/{class_id}")
async def delete_share_class(
    class_id: str,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/share-classes/{class_id}",
        params={"actor": _actor(current_user)},
    )


@router.post("/portfolio-managers", status_code=201)
async def create_portfolio_manager(
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/data-management/portfolio-managers",
        params={"actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/portfolio-managers")
async def update_portfolio_manager(
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
    port_id: str = Query(...),
    person_id: str = Query(...),
    role: str = Query(...),
    begin_date: date = Query(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        "/data-management/portfolio-managers",
        params={
            "actor": _actor(current_user),
            "port_id": port_id,
            "person_id": person_id,
            "role": role,
            "begin_date": begin_date,
        },
        json=payload,
    )


@router.delete("/portfolio-managers")
async def delete_portfolio_manager(
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    port_id: str = Query(...),
    person_id: str = Query(...),
    role: str = Query(...),
    begin_date: date = Query(...),
) -> Any:
    return await _proxy(
        client,
        "delete",
        "/data-management/portfolio-managers",
        params={
            "actor": _actor(current_user),
            "port_id": port_id,
            "person_id": person_id,
            "role": role,
            "begin_date": begin_date,
        },
    )

@router.post("/valuation-sheet/{fund_id}", status_code=201)
async def create_valuation_sheet_row(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/valuation-sheet/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/valuation-sheet/{fund_id}/{subject_code}")
async def update_valuation_sheet_row(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/valuation-sheet/{fund_id}/{subject_code}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/valuation-sheet/{fund_id}/{subject_code}")
async def delete_valuation_sheet_row(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/valuation-sheet/{fund_id}/{subject_code}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
    )


@router.post("/portfolio-nav/{fund_id}", status_code=201)
async def create_portfolio_nav(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/portfolio-nav/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/portfolio-nav/{fund_id}/{currency}")
async def update_portfolio_nav(
    fund_id: str,
    currency: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/portfolio-nav/{fund_id}/{currency}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/portfolio-nav/{fund_id}/{currency}")
async def delete_portfolio_nav(
    fund_id: str,
    currency: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/portfolio-nav/{fund_id}/{currency}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
    )


@router.post("/portfolio-mmf/{fund_id}", status_code=201)
async def create_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "post",
        f"/data-management/portfolio-mmf/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.patch("/portfolio-mmf/{fund_id}")
async def update_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    return await _proxy(
        client,
        "patch",
        f"/data-management/portfolio-mmf/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
        json=payload,
    )


@router.delete("/portfolio-mmf/{fund_id}")
async def delete_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    current_user: PortfolioAdmin,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/data-management/portfolio-mmf/{fund_id}",
        params={"as_of_date": as_of_date, "actor": _actor(current_user)},
    )
