"""Data-management workbench APIs for editable positions, market quotes and simulations."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...tools.performance.investment_analysis import compute_pretrade_risk_budget
from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


async def _audit(
    db: AsyncSession,
    *,
    event_type: str,
    actor: str,
    port_id: str | None,
    details: dict[str, Any],
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO fsi.svc_wf_audit_log (event_type, actor, port_id, details)
            VALUES (:event_type, :actor, :port_id, CAST(:details AS jsonb))
            """
        ),
        {
            "event_type": event_type,
            "actor": actor,
            "port_id": port_id,
            "details": json.dumps(details, default=str, ensure_ascii=False),
        },
    )


class PositionCreate(BaseModel):
    subject_code: str = Field(min_length=1, max_length=32)
    subject_name: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0)
    data_source: str = Field(default="MANUAL", min_length=1, max_length=32)
    memo: str | None = Field(default=None, max_length=200)

    @field_validator("subject_code", "subject_name", "data_source")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def derive_market_value(self) -> "PositionCreate":
        if self.market_value is None:
            if self.quantity is None or self.unit_price is None:
                raise ValueError("market_value or both quantity and unit_price are required")
            self.market_value = self.quantity * self.unit_price
        return self


class PositionUpdate(BaseModel):
    subject_name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0)
    data_source: str | None = Field(default=None, min_length=1, max_length=32)
    memo: str | None = Field(default=None, max_length=200)

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class MarketQuoteCreate(BaseModel):
    price_date: date
    security_code: str = Field(min_length=1, max_length=32)
    market_id: str = Field(min_length=1, max_length=16)
    price_type: str = Field(default="CLOSE", min_length=1, max_length=16)
    open_price: Decimal | None = Field(default=None, ge=0)
    high_price: Decimal | None = Field(default=None, ge=0)
    low_price: Decimal | None = Field(default=None, ge=0)
    close_price: Decimal = Field(gt=0)
    prev_close: Decimal | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    turnover: Decimal | None = Field(default=None, ge=0)
    data_source: str = Field(default="MANUAL", min_length=1, max_length=16)

    @field_validator("security_code", "market_id", "price_type", "data_source")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_ohlc(self) -> "MarketQuoteCreate":
        if self.high_price is not None and self.low_price is not None:
            if self.high_price < self.low_price:
                raise ValueError("high_price must not be lower than low_price")
            if not self.low_price <= self.close_price <= self.high_price:
                raise ValueError("close_price must be between low_price and high_price")
        return self


class MarketQuoteUpdate(BaseModel):
    market_id: str | None = Field(default=None, min_length=1, max_length=16)
    open_price: Decimal | None = Field(default=None, ge=0)
    high_price: Decimal | None = Field(default=None, ge=0)
    low_price: Decimal | None = Field(default=None, ge=0)
    close_price: Decimal | None = Field(default=None, gt=0)
    prev_close: Decimal | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    turnover: Decimal | None = Field(default=None, ge=0)
    data_source: str | None = Field(default=None, min_length=1, max_length=16)

    @field_validator("market_id", "data_source")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class SimulatedOrderCreate(BaseModel):
    as_of_date: date
    trade_date: date
    trade_side: Literal["BUY", "SELL"]
    asset_class: str = Field(min_length=1, max_length=32)
    security_code: str = Field(min_length=1, max_length=32)
    security_name: str | None = Field(default=None, max_length=200)
    issuer_name: str | None = Field(default=None, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    trade_amount: Decimal | None = Field(default=None, gt=0)
    duration_years: Decimal = Field(default=0, ge=0, le=30)
    notes: str | None = None

    @field_validator("asset_class", "security_code", "currency")
    @classmethod
    def normalize_order_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def derive_trade_amount(self) -> "SimulatedOrderCreate":
        if self.trade_amount is None:
            if self.quantity is None or self.price is None:
                raise ValueError("trade_amount or both quantity and price are required")
            self.trade_amount = self.quantity * self.price
        return self


class SimulatedOrderUpdate(BaseModel):
    as_of_date: date | None = None
    trade_date: date | None = None
    trade_side: Literal["BUY", "SELL"] | None = None
    asset_class: str | None = Field(default=None, min_length=1, max_length=32)
    security_code: str | None = Field(default=None, min_length=1, max_length=32)
    security_name: str | None = Field(default=None, max_length=200)
    issuer_name: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    trade_amount: Decimal | None = Field(default=None, gt=0)
    duration_years: Decimal | None = Field(default=None, ge=0, le=30)
    notes: str | None = None

    @field_validator("asset_class", "security_code", "currency")
    @classmethod
    def normalize_optional_order_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


async def _get_position(
    db: AsyncSession, fund_id: str, as_of_date: date, subject_code: str
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT evaluate_date, port_id, subject_code, subject_name, currency,
                       quantity, unit_price, cost, market_value, weight_pct,
                       data_source, memo, loaded_at
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fund_id AND evaluate_date = :as_of_date
                  AND subject_code = :subject_code
                """
            ),
            {
                "fund_id": fund_id,
                "as_of_date": as_of_date,
                "subject_code": subject_code,
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Position not found")
    return _row_dict(row)


@router.get("/positions/{fund_id}", summary="查詢可編輯估值持倉")
async def list_positions(
    fund_id: str,
    as_of_date: date,
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    params = {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "search": pattern,
        "limit": limit,
    }
    where = """
        WHERE port_id = :fund_id AND evaluate_date = :as_of_date
          AND (CAST(:search AS text) IS NULL
               OR subject_code ILIKE CAST(:search AS text)
               OR subject_name ILIKE CAST(:search AS text))
    """
    count = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM fsi.balance_valuation_sheet {where}"), params
        )
    ).scalar_one()
    rows = (
        await db.execute(
            text(
                f"""
                SELECT evaluate_date, port_id, subject_code, subject_name, currency,
                       quantity, unit_price, cost, market_value, weight_pct,
                       data_source, memo, loaded_at
                FROM fsi.balance_valuation_sheet {where}
                ORDER BY weight_pct DESC NULLS LAST, subject_code
                LIMIT :limit
                """
            ),
            params,
        )
    ).all()
    return {"items": [_row_dict(row) for row in rows], "count": int(count)}


@router.post("/positions/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_position(
    fund_id: str,
    as_of_date: date,
    payload: PositionCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.balance_valuation_sheet
                    (evaluate_date, port_id, subject_code, subject_name, currency,
                     quantity, unit_price, cost, market_value, weight_pct,
                     data_source, memo)
                VALUES
                    (:as_of_date, :fund_id, :subject_code, :subject_name, :currency,
                     :quantity, :unit_price, :cost, :market_value, :weight_pct,
                     :data_source, :memo)
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, **values},
        )
        await _audit(
            db,
            event_type="POSITION_CREATED",
            actor=actor,
            port_id=fund_id,
            details={"as_of_date": as_of_date, "position": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Position already exists") from exc
    return await _get_position(db, fund_id, as_of_date, payload.subject_code)


@router.patch("/positions/{fund_id}/{subject_code}")
async def update_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    payload: PositionUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_position(db, fund_id, as_of_date, subject_code)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "market_value" not in values and ({"quantity", "unit_price"} & values.keys()):
        quantity = values.get("quantity", previous.get("quantity"))
        unit_price = values.get("unit_price", previous.get("unit_price"))
        if quantity is not None and unit_price is not None:
            values["market_value"] = quantity * unit_price
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.balance_valuation_sheet SET {assignments}, loaded_at = NOW()
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
              AND subject_code = :subject_code
            """
        ),
        {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "subject_code": subject_code,
            **values,
        },
    )
    await _audit(
        db,
        event_type="POSITION_UPDATED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_position(db, fund_id, as_of_date, subject_code)


@router.delete("/positions/{fund_id}/{subject_code}")
async def delete_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_position(db, fund_id, as_of_date, subject_code)
    await db.execute(
        text(
            """
            DELETE FROM fsi.balance_valuation_sheet
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
              AND subject_code = :subject_code
            """
        ),
        {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "subject_code": subject_code,
        },
    )
    await _audit(
        db,
        event_type="POSITION_DELETED",
        actor=actor,
        port_id=fund_id,
        details={"position": previous},
    )
    await db.commit()
    return {"message": "Position deleted"}


async def _get_market_quote(
    db: AsyncSession, price_date: date, security_code: str, price_type: str
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT price_date, security_code, market_id, price_type,
                       open_price, high_price, low_price, close_price, prev_close,
                       price_change_pct, volume, turnover, data_source, loaded_at
                FROM fsi.mktdata_quotes
                WHERE price_date = :price_date AND security_code = :security_code
                  AND price_type = :price_type
                """
            ),
            {
                "price_date": price_date,
                "security_code": security_code,
                "price_type": price_type,
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Market quote not found")
    return _row_dict(row)


@router.get("/market-quotes", summary="查詢市場行情")
async def list_market_quotes(
    price_date: date,
    search: str | None = None,
    market_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    params = {
        "price_date": price_date,
        "search": pattern,
        "market_id": market_id.strip().upper() if market_id else None,
        "limit": limit,
    }
    where = """
        WHERE price_date = :price_date
          AND (CAST(:search AS text) IS NULL OR security_code ILIKE CAST(:search AS text))
          AND (CAST(:market_id AS text) IS NULL OR market_id = CAST(:market_id AS text))
    """
    count = (
        await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_quotes {where}"), params)
    ).scalar_one()
    rows = (
        await db.execute(
            text(
                f"""
                SELECT price_date, security_code, market_id, price_type,
                       open_price, high_price, low_price, close_price, prev_close,
                       price_change_pct, volume, turnover, data_source, loaded_at
                FROM fsi.mktdata_quotes {where}
                ORDER BY market_id, security_code, price_type
                LIMIT :limit
                """
            ),
            params,
        )
    ).all()
    return {"items": [_row_dict(row) for row in rows], "count": int(count)}


@router.get("/market-quotes/history/{security_code}", summary="行情時序")
async def market_quote_history(
    security_code: str,
    start: date,
    end: date,
    price_type: str = "CLOSE",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if start > end:
        raise HTTPException(status_code=422, detail="start must not be later than end")
    rows = (
        await db.execute(
            text(
                """
                SELECT price_date, security_code, market_id, price_type,
                       close_price, price_change_pct, volume, turnover, data_source
                FROM fsi.mktdata_quotes
                WHERE security_code = :security_code AND price_type = :price_type
                  AND price_date BETWEEN :start AND :end
                ORDER BY price_date
                """
            ),
            {
                "security_code": security_code.strip().upper(),
                "price_type": price_type.strip().upper(),
                "start": start,
                "end": end,
            },
        )
    ).all()
    return {"items": [_row_dict(row) for row in rows], "count": len(rows)}


@router.post("/market-quotes", status_code=status.HTTP_201_CREATED)
async def create_market_quote(
    payload: MarketQuoteCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    if payload.prev_close:
        values["price_change_pct"] = (
            (payload.close_price - payload.prev_close) / payload.prev_close * 100
        )
    else:
        values["price_change_pct"] = None
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.mktdata_quotes
                    (price_date, security_code, market_id, price_type, open_price,
                     high_price, low_price, close_price, prev_close, price_change_pct,
                     volume, turnover, data_source)
                VALUES
                    (:price_date, :security_code, :market_id, :price_type, :open_price,
                     :high_price, :low_price, :close_price, :prev_close, :price_change_pct,
                     :volume, :turnover, :data_source)
                """
            ),
            values,
        )
        await _audit(
            db,
            event_type="MARKET_QUOTE_CREATED",
            actor=actor,
            port_id=None,
            details={"quote": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Market quote already exists") from exc
    return await _get_market_quote(
        db, payload.price_date, payload.security_code, payload.price_type
    )


@router.patch("/market-quotes/{price_date}/{security_code}/{price_type}")
async def update_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    payload: MarketQuoteUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_market_quote(db, price_date, security_code, price_type)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    merged = {**previous, **values}
    high, low, close = merged.get("high_price"), merged.get("low_price"), merged.get("close_price")
    if high is not None and low is not None:
        if high < low or not low <= close <= high:
            raise HTTPException(status_code=422, detail="Invalid OHLC range")
    prev_close = merged.get("prev_close")
    values["price_change_pct"] = (
        (close - prev_close) / prev_close * 100 if prev_close else None
    )
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.mktdata_quotes SET {assignments}, loaded_at = NOW()
            WHERE price_date = :price_date AND security_code = :security_code
              AND price_type = :price_type
            """
        ),
        {
            "price_date": price_date,
            "security_code": security_code,
            "price_type": price_type,
            **values,
        },
    )
    await _audit(
        db,
        event_type="MARKET_QUOTE_UPDATED",
        actor=actor,
        port_id=None,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_market_quote(db, price_date, security_code, price_type)


@router.delete("/market-quotes/{price_date}/{security_code}/{price_type}")
async def delete_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_market_quote(db, price_date, security_code, price_type)
    await db.execute(
        text(
            """
            DELETE FROM fsi.mktdata_quotes
            WHERE price_date = :price_date AND security_code = :security_code
              AND price_type = :price_type
            """
        ),
        {
            "price_date": price_date,
            "security_code": security_code,
            "price_type": price_type,
        },
    )
    await _audit(
        db,
        event_type="MARKET_QUOTE_DELETED",
        actor=actor,
        port_id=None,
        details={"quote": previous},
    )
    await db.commit()
    return {"message": "Market quote deleted"}


async def _get_simulated_order(
    db: AsyncSession, order_id: UUID, fund_id: str | None = None
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT * FROM fsi.transact_simulated_order
                WHERE order_id = :order_id
                  AND (CAST(:fund_id AS text) IS NULL OR port_id = CAST(:fund_id AS text))
                """
            ),
            {"order_id": order_id, "fund_id": fund_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Simulated order not found")
    return _row_dict(row)


@router.get("/simulated-orders/{fund_id}")
async def list_simulated_orders(
    fund_id: str,
    as_of_date: date | None = None,
    include_cancelled: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT * FROM fsi.transact_simulated_order
                WHERE port_id = :fund_id
                  AND (CAST(:as_of_date AS date) IS NULL OR as_of_date = CAST(:as_of_date AS date))
                  AND (:include_cancelled OR status <> 'CANCELLED')
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {
                "fund_id": fund_id,
                "as_of_date": as_of_date,
                "include_cancelled": include_cancelled,
                "limit": limit,
            },
        )
    ).all()
    return {"items": [_row_dict(row) for row in rows], "count": len(rows)}


@router.post("/simulated-orders/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_simulated_order(
    fund_id: str,
    payload: SimulatedOrderCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    row = (
        await db.execute(
            text(
                """
                INSERT INTO fsi.transact_simulated_order
                    (port_id, as_of_date, trade_date, trade_side, asset_class,
                     security_code, security_name, issuer_name, currency,
                     quantity, price, trade_amount, duration_years, notes, created_by)
                VALUES
                    (:fund_id, :as_of_date, :trade_date, :trade_side, :asset_class,
                     :security_code, :security_name, :issuer_name, :currency,
                     :quantity, :price, :trade_amount, :duration_years, :notes, :actor)
                RETURNING order_id
                """
            ),
            {"fund_id": fund_id, "actor": actor, **values},
        )
    ).first()
    order_id = row.order_id
    await _audit(
        db,
        event_type="SIMULATED_ORDER_CREATED",
        actor=actor,
        port_id=fund_id,
        details={"order_id": order_id, "order": values},
    )
    await db.commit()
    return await _get_simulated_order(db, order_id)


@router.patch("/simulated-orders/{fund_id}/{order_id}")
async def update_simulated_order(
    fund_id: str,
    order_id: UUID,
    payload: SimulatedOrderUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_simulated_order(db, order_id, fund_id)
    if previous["status"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="Cancelled order cannot be edited")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "trade_amount" not in values:
        quantity = values.get("quantity", previous.get("quantity"))
        price = values.get("price", previous.get("price"))
        if quantity is not None and price is not None:
            values["trade_amount"] = quantity * price
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.transact_simulated_order
            SET {assignments}, status = 'DRAFT', decision = NULL,
                breach_flags = '[]'::jsonb, validation_result = NULL,
                updated_by = :actor, updated_at = NOW()
            WHERE order_id = :order_id
            """
        ),
        {"order_id": order_id, "actor": actor, **values},
    )
    await _audit(
        db,
        event_type="SIMULATED_ORDER_UPDATED",
        actor=actor,
        port_id=str(previous["port_id"]),
        details={"order_id": order_id, "before": previous, "changes": values},
    )
    await db.commit()
    return await _get_simulated_order(db, order_id)


def _simulation_status(decision: str) -> str:
    return {
        "ALLOW": "VALIDATED",
        "ALLOW_WITH_WARNING": "WARNING",
        "BLOCK": "BLOCKED",
    }.get(decision, "BLOCKED")


@router.post("/simulated-orders/{fund_id}/{order_id}/validate")
async def validate_simulated_order(
    fund_id: str,
    order_id: UUID,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _get_simulated_order(db, order_id, fund_id)
    if order["status"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="Cancelled order cannot be validated")
    result = await compute_pretrade_risk_budget(
        fund_id=str(order["port_id"]),
        as_of_date=order["as_of_date"],
        trade_amount=float(order["trade_amount"]),
        trade_side=str(order["trade_side"]),
        asset_class=str(order["asset_class"]),
        duration_years=float(order["duration_years"]),
        issuer_name=str(order["issuer_name"] or "UNKNOWN_ISSUER"),
        db=db,
    )
    decision = str(result["decision"])
    new_status = _simulation_status(decision)
    breach_flags = list(result.get("breach_flags", []))
    await db.execute(
        text(
            """
            UPDATE fsi.transact_simulated_order
            SET status = :status, decision = :decision,
                breach_flags = CAST(:breach_flags AS jsonb),
                validation_result = CAST(:validation_result AS jsonb),
                updated_by = :actor, updated_at = NOW()
            WHERE order_id = :order_id
            """
        ),
        {
            "order_id": order_id,
            "status": new_status,
            "decision": decision,
            "breach_flags": json.dumps(breach_flags, ensure_ascii=False),
            "validation_result": json.dumps(result, default=str, ensure_ascii=False),
            "actor": actor,
        },
    )
    await _audit(
        db,
        event_type="SIMULATED_ORDER_VALIDATED",
        actor=actor,
        port_id=str(order["port_id"]),
        details={
            "order_id": order_id,
            "decision": decision,
            "status": new_status,
            "breach_flags": breach_flags,
        },
    )
    await db.commit()
    return await _get_simulated_order(db, order_id)


@router.delete("/simulated-orders/{fund_id}/{order_id}")
async def cancel_simulated_order(
    fund_id: str,
    order_id: UUID,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    order = await _get_simulated_order(db, order_id, fund_id)
    if order["status"] != "CANCELLED":
        await db.execute(
            text(
                """
                UPDATE fsi.transact_simulated_order
                SET status = 'CANCELLED', updated_by = :actor, updated_at = NOW()
                WHERE order_id = :order_id
                """
            ),
            {"order_id": order_id, "actor": actor},
        )
        await _audit(
            db,
            event_type="SIMULATED_ORDER_CANCELLED",
            actor=actor,
            port_id=str(order["port_id"]),
            details={"order_id": order_id, "previous_status": order["status"]},
        )
        await db.commit()
    return await _get_simulated_order(db, order_id)


# ── Portfolio master data (fsi.para_portfolio) ───────────────────
PortfolioType = Literal[
    "MMF", "BOND", "EQUITY", "BALANCED", "INDEX", "ETF",
    "HEDGE", "PRIVATE", "PENSION", "MANDATE", "SMA", "OTHER",
]

_PORTFOLIO_COLUMNS = """
    port_id, port_name, port_name_en, port_type::text AS port_type,
    base_currency, inception_date, is_active, is_mmf, sfc_code,
    mmf_wam_limit_days, mmf_wal_limit_days, mgmt_fee_bps, updated_at
"""


class PortfolioCreate(BaseModel):
    port_id: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    port_name: str = Field(min_length=1, max_length=120)
    port_name_en: str | None = Field(default=None, max_length=120)
    port_type: PortfolioType
    base_currency: str = Field(default="HKD", min_length=3, max_length=3)
    inception_date: date
    is_mmf: bool = False
    sfc_code: str | None = Field(default=None, max_length=32)
    mmf_wam_limit_days: int | None = Field(default=None, ge=1, le=365)
    mmf_wal_limit_days: int | None = Field(default=None, ge=1, le=730)
    mgmt_fee_bps: Decimal | None = Field(default=None, ge=0)

    @field_validator("port_id", mode="before")
    @classmethod
    def upper_port_id(cls, value: Any) -> Any:
        # Run before the pattern constraint so surrounding whitespace is tolerated.
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("base_currency")
    @classmethod
    def upper_currency(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioUpdate(BaseModel):
    port_name: str | None = Field(default=None, min_length=1, max_length=120)
    port_name_en: str | None = Field(default=None, max_length=120)
    port_type: PortfolioType | None = None
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)
    inception_date: date | None = None
    is_active: bool | None = None
    is_mmf: bool | None = None
    sfc_code: str | None = Field(default=None, max_length=32)
    mmf_wam_limit_days: int | None = Field(default=None, ge=1, le=365)
    mmf_wal_limit_days: int | None = Field(default=None, ge=1, le=730)
    mgmt_fee_bps: Decimal | None = Field(default=None, ge=0)

    @field_validator("base_currency")
    @classmethod
    def upper_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


async def _get_portfolio(db: AsyncSession, port_id: str) -> dict[str, Any]:
    row = (
        await db.execute(
            text(f"SELECT {_PORTFOLIO_COLUMNS} FROM fsi.para_portfolio WHERE port_id = :pid"),
            {"pid": port_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return _row_dict(row)


@router.get("/portfolios", summary="組合主數據列表")
async def list_portfolios(
    search: str | None = None,
    include_inactive: bool = True,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                f"""
                SELECT {_PORTFOLIO_COLUMNS} FROM fsi.para_portfolio
                WHERE (:include_inactive OR is_active = TRUE)
                  AND (CAST(:search AS text) IS NULL
                       OR port_id ILIKE CAST(:search AS text)
                       OR port_name ILIKE CAST(:search AS text))
                ORDER BY is_active DESC, port_id
                """
            ),
            {"include_inactive": include_inactive, "search": pattern},
        )
    ).all()
    return {"items": [_row_dict(r) for r in rows], "count": len(rows)}


@router.post("/portfolios", status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.para_portfolio
                    (port_id, port_name, port_name_en, port_type, base_currency,
                     inception_date, is_mmf, sfc_code, mmf_wam_limit_days,
                     mmf_wal_limit_days, mgmt_fee_bps)
                VALUES
                    (:port_id, :port_name, :port_name_en, CAST(:port_type AS fsi.portfolio_type),
                     :base_currency, :inception_date, :is_mmf, :sfc_code,
                     :mmf_wam_limit_days, :mmf_wal_limit_days, :mgmt_fee_bps)
                """
            ),
            values,
        )
        await _audit(
            db,
            event_type="PORTFOLIO_CREATED",
            actor=actor,
            port_id=payload.port_id,
            details={"portfolio": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Portfolio already exists") from exc
    return await _get_portfolio(db, payload.port_id)


@router.patch("/portfolios/{port_id}")
async def update_portfolio(
    port_id: str,
    payload: PortfolioUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    port_id = port_id.strip().upper()
    previous = await _get_portfolio(db, port_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(
        (f"{col} = CAST(:{col} AS fsi.portfolio_type)" if col == "port_type" else f"{col} = :{col}")
        for col in values
    )
    await db.execute(
        text(
            f"""
            UPDATE fsi.para_portfolio SET {assignments}, updated_at = NOW()
            WHERE port_id = :port_id
            """
        ),
        {"port_id": port_id, **values},
    )
    await _audit(
        db,
        event_type="PORTFOLIO_UPDATED",
        actor=actor,
        port_id=port_id,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_portfolio(db, port_id)


@router.delete("/portfolios/{port_id}")
async def delete_portfolio(
    port_id: str,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    port_id = port_id.strip().upper()
    previous = await _get_portfolio(db, port_id)
    # Guard: refuse hard-delete when dependent data exists; suggest deactivate.
    dependent = (
        await db.execute(
            text(
                """
                SELECT
                  EXISTS(SELECT 1 FROM fsi.balance_portfolio_nav WHERE port_id = :pid)
                  OR EXISTS(SELECT 1 FROM fsi.balance_valuation_sheet WHERE port_id = :pid)
                  OR EXISTS(SELECT 1 FROM fsi.transact_simulated_order WHERE port_id = :pid)
                """
            ),
            {"pid": port_id},
        )
    ).scalar_one()
    if dependent:
        raise HTTPException(
            status_code=409,
            detail="Portfolio has related data (NAV / valuation / simulated orders); deactivate it instead of deleting",
        )
    await db.execute(text("DELETE FROM fsi.para_portfolio WHERE port_id = :pid"), {"pid": port_id})
    await _audit(
        db,
        event_type="PORTFOLIO_DELETED",
        actor=actor,
        port_id=port_id,
        details={"portfolio": previous},
    )
    await db.commit()
    return {"message": "Portfolio deleted"}