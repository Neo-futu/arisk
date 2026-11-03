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

MANAGED_ENTITIES: list[dict[str, Any]] = [
    {
        "id": "portfolios",
        "table": "fsi.para_portfolio",
        "label": "组合主数据",
        "description": "组合档案、份额/人员，以及估值表与净值快照；用选表切换 CRUD 目标",
        "ops": ["list", "create", "update", "delete"],
        "date_field": None,
        "fund_scoped": False,
        "tables": [
            {"id": "para_portfolio", "table": "fsi.para_portfolio", "label": "组合主数据"},
            {"id": "para_share_class", "table": "fsi.para_share_class", "label": "份额类别"},
            {"id": "para_portfolio_manager", "table": "fsi.para_portfolio_manager", "label": "组合人员"},
            {"id": "balance_valuation_sheet", "table": "fsi.balance_valuation_sheet", "label": "估值表"},
            {"id": "balance_portfolio_nav", "table": "fsi.balance_portfolio_nav", "label": "组合净值"},
            {"id": "balance_portfolio_mmf", "table": "fsi.balance_portfolio_mmf", "label": "货基净值指标"},
        ],
    },
    {
        "id": "positions",
        "table": "fsi.balance_bond",
        "label": "持仓明细（证券）",
        "description": "按资产表维护证券级持仓；可选单表或全部汇总",
        "ops": ["list", "create", "update", "delete"],
        "date_field": "evaluate_date",
        "fund_scoped": True,
        "tables": [
            {"id": "all", "table": "(union)", "label": "全部持仓", "asset_class": None},
            {"id": "balance_bond", "table": "fsi.balance_bond", "label": "债券", "asset_class": "BOND"},
            {"id": "balance_cd", "table": "fsi.balance_cd", "label": "存单 CD", "asset_class": "CD"},
            {"id": "balance_deposit", "table": "fsi.balance_deposit", "label": "定期存款", "asset_class": "DEPOSIT"},
            {"id": "balance_cash", "table": "fsi.balance_cash", "label": "现金", "asset_class": "CASH"},
            {"id": "balance_stock", "table": "fsi.balance_stock", "label": "股票", "asset_class": "STOCK"},
            {"id": "balance_fund", "table": "fsi.balance_fund", "label": "基金", "asset_class": "FUND"},
            {"id": "balance_repo", "table": "fsi.balance_repo", "label": "回购", "asset_class": "REPO"},
        ],
    },
    {
        "id": "market",
        "table": "fsi.mktdata_quotes",
        "label": "市场行情",
        "description": "个券/指数/期货/汇率/基金 NAV 等行情表；选表后 CRUD",
        "ops": ["list", "create", "update", "delete", "history"],
        "date_field": "price_date",
        "fund_scoped": False,
        "tables": [
            {"id": "mktdata_quotes", "table": "fsi.mktdata_quotes", "label": "通用行情"},
            {"id": "mktdata_index_quotes", "table": "fsi.mktdata_index_quotes", "label": "指数行情"},
            {"id": "mktdata_futures_quotes", "table": "fsi.mktdata_futures_quotes", "label": "期货行情"},
            {"id": "mktdata_fx_rate", "table": "fsi.mktdata_fx_rate", "label": "汇率"},
            {"id": "mktdata_fund_nav", "table": "fsi.mktdata_fund_nav", "label": "基金 NAV"},
            {"id": "mktdata_security_quotes", "table": "fsi.mktdata_security_quotes", "label": "证券原始行情"},
        ],
    },
    {
        "id": "trades",
        "table": "fsi.transact_simulated_order",
        "label": "模拟交易",
        "description": "交易前试算草稿；入口在交易管理菜单",
        "ops": ["list", "create", "update", "validate", "cancel"],
        "date_field": "as_of_date",
        "fund_scoped": True,
        "workbench_hidden": True,
        "tables": [
            {"id": "transact_simulated_order", "table": "fsi.transact_simulated_order", "label": "模拟订单"},
        ],
    },
]

_POSITION_TABLE_TO_CLASS = {
    "balance_bond": "BOND",
    "balance_cd": "CD",
    "balance_deposit": "DEPOSIT",
    "balance_cash": "CASH",
    "balance_stock": "STOCK",
    "balance_fund": "FUND",
    "balance_repo": "REPO",
    "fsi.balance_bond": "BOND",
    "fsi.balance_cd": "CD",
    "fsi.balance_deposit": "DEPOSIT",
    "fsi.balance_cash": "CASH",
    "fsi.balance_stock": "STOCK",
    "fsi.balance_fund": "FUND",
    "fsi.balance_repo": "REPO",
}

_MARKET_TABLE_IDS = {
    "mktdata_quotes",
    "mktdata_index_quotes",
    "mktdata_futures_quotes",
    "mktdata_fx_rate",
    "mktdata_fund_nav",
    "mktdata_security_quotes",
}


def _normalize_position_table(table: str | None) -> str | None:
    if not table or table in {"all", "*", "(union)"}:
        return None
    key = table.strip().lower().removeprefix("fsi.")
    if key not in _POSITION_TABLE_TO_CLASS:
        raise HTTPException(status_code=422, detail=f"Unsupported position table: {table}")
    return key


def _normalize_market_table(table: str | None) -> str:
    key = (table or "mktdata_quotes").strip().lower().removeprefix("fsi.")
    if key not in _MARKET_TABLE_IDS:
        raise HTTPException(status_code=422, detail=f"Unsupported market table: {table}")
    return key


_PORTFOLIO_TABLE_IDS = {
    "para_portfolio",
    "para_share_class",
    "para_portfolio_manager",
    "balance_valuation_sheet",
    "balance_portfolio_nav",
    "balance_portfolio_mmf",
}

_PORTFOLIO_DATE_SCOPED = {
    "balance_valuation_sheet",
    "balance_portfolio_nav",
    "balance_portfolio_mmf",
}


def _normalize_portfolio_table(table: str | None) -> str:
    key = (table or "para_portfolio").strip().lower().removeprefix("fsi.")
    if key not in _PORTFOLIO_TABLE_IDS:
        raise HTTPException(status_code=422, detail=f"Unsupported portfolio table: {table}")
    return key


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


_ASSET_CLASSES = ("BOND", "CD", "DEPOSIT", "CASH", "STOCK", "FUND", "REPO")


class PositionCreate(BaseModel):
    asset_class: Literal["BOND", "CD", "DEPOSIT", "CASH", "STOCK", "FUND", "REPO"] = "BOND"
    subject_code: str = Field(min_length=1, max_length=64)
    subject_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0)
    maturity_date: date | None = None
    issuer_name: str | None = Field(default=None, max_length=200)
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

    @field_validator("asset_class")
    @classmethod
    def normalize_asset_class(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def derive_market_value(self) -> "PositionCreate":
        if self.market_value is None:
            if self.quantity is None or self.unit_price is None:
                raise ValueError("market_value or both quantity and unit_price are required")
            self.market_value = self.quantity * self.unit_price
        return self


class PositionUpdate(BaseModel):
    asset_class: Literal["BOND", "CD", "DEPOSIT", "CASH", "STOCK", "FUND", "REPO"] | None = None
    subject_name: str | None = Field(default=None, min_length=1, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0)
    maturity_date: date | None = None
    issuer_name: str | None = Field(default=None, max_length=200)
    data_source: str | None = Field(default=None, min_length=1, max_length=32)
    memo: str | None = Field(default=None, max_length=200)

    @field_validator("currency", "asset_class")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
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


async def _latest_holdings_date(db: AsyncSession, fund_id: str, cutoff: date) -> date | None:
    return (
        await db.execute(
            text(
                """
                SELECT MAX(d) FROM (
                    SELECT MAX(evaluate_date) AS d FROM fsi.balance_bond
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_cd
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_deposit
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_cash
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_stock
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_fund
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                    UNION ALL
                    SELECT MAX(evaluate_date) FROM fsi.balance_repo
                     WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                ) s
                """
            ),
            {"fund_id": fund_id, "cutoff": cutoff},
        )
    ).scalar_one()


_HOLDINGS_UNION_SQL = """
SELECT * FROM (
    SELECT evaluate_date, port_id, 'BOND'::text AS asset_class,
           security_code AS subject_code, COALESCE(security_name, security_code) AS subject_name,
           currency, quantity, COALESCE(dirty_price, clean_price) AS unit_price, cost,
           market_value, weight_pct, maturity_date, issuer_name,
           'fsi.balance_bond'::text AS source_table, loaded_at
    FROM fsi.balance_bond
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'CD',
           security_code, COALESCE(security_name, security_code),
           currency, quantity, price, cost,
           market_value, weight_pct, maturity_date, issuer_name,
           'fsi.balance_cd', loaded_at
    FROM fsi.balance_cd
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'DEPOSIT',
           deposit_id, COALESCE(deposit_name, deposit_id),
           currency, NULL::numeric, NULL::numeric, NULL::numeric,
           COALESCE(total_value, principal), weight_pct, maturity_date, bank_name,
           'fsi.balance_deposit', loaded_at
    FROM fsi.balance_deposit
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'CASH',
           cash_account_id, COALESCE(account_name, cash_account_id),
           currency, NULL::numeric, NULL::numeric, NULL::numeric,
           amount, weight_pct, NULL::date, bank_id,
           'fsi.balance_cash', loaded_at
    FROM fsi.balance_cash
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'STOCK',
           security_code, COALESCE(security_name, security_code),
           currency, quantity, price, cost,
           market_value, weight_pct, NULL::date, sector,
           'fsi.balance_stock', loaded_at
    FROM fsi.balance_stock
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'FUND',
           security_code, COALESCE(security_name, security_code),
           currency, quantity, NULL::numeric, cost,
           market_value, weight_pct, NULL::date, NULL::text,
           'fsi.balance_fund', loaded_at
    FROM fsi.balance_fund
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
    UNION ALL
    SELECT evaluate_date, port_id, 'REPO',
           repo_id, COALESCE(pledged_security_name, repo_id),
           currency, NULL::numeric, NULL::numeric, NULL::numeric,
           COALESCE(total_value, principal), weight_pct, maturity_date, counterparty_name,
           'fsi.balance_repo', loaded_at
    FROM fsi.balance_repo
    WHERE port_id = :fund_id AND evaluate_date = :as_of_date
) holdings
WHERE (CAST(:search AS text) IS NULL
       OR subject_code ILIKE CAST(:search AS text)
       OR subject_name ILIKE CAST(:search AS text)
       OR asset_class ILIKE CAST(:search AS text))
ORDER BY weight_pct DESC NULLS LAST, asset_class, subject_code
LIMIT :limit
"""


async def _list_security_positions(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    search: str | None,
    limit: int,
    table: str | None = None,
) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    table_key = _normalize_position_table(table)
    asset_class = _POSITION_TABLE_TO_CLASS.get(table_key) if table_key else None
    params: dict[str, Any] = {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "search": pattern,
        "limit": limit,
        "asset_class": asset_class,
    }
    sql = _HOLDINGS_UNION_SQL.replace(
        ") holdings\nWHERE (CAST(:search AS text) IS NULL",
        ") holdings\nWHERE (CAST(:asset_class AS text) IS NULL OR asset_class = CAST(:asset_class AS text))\n"
        "  AND (CAST(:search AS text) IS NULL",
    )
    rows = (await db.execute(text(sql), params)).all()
    return [_row_dict(row) for row in rows]


async def _get_position(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    subject_code: str,
    asset_class: str | None = None,
) -> dict[str, Any]:
    items = await _list_security_positions(db, fund_id, as_of_date, subject_code, 200)
    matches = [
        item
        for item in items
        if str(item.get("subject_code")) == subject_code
        and (asset_class is None or str(item.get("asset_class")) == asset_class.upper())
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Position not found")
    return matches[0]


def _table_key_for_asset_class(asset_class: str) -> tuple[str, str]:
    mapping = {
        "BOND": ("fsi.balance_bond", "security_code"),
        "CD": ("fsi.balance_cd", "security_code"),
        "DEPOSIT": ("fsi.balance_deposit", "deposit_id"),
        "CASH": ("fsi.balance_cash", "cash_account_id"),
        "STOCK": ("fsi.balance_stock", "security_code"),
        "FUND": ("fsi.balance_fund", "security_code"),
        "REPO": ("fsi.balance_repo", "repo_id"),
    }
    try:
        return mapping[asset_class.upper()]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unsupported asset_class: {asset_class}") from exc


@router.get("/catalog", summary="数据管理可维护表目录")
async def data_management_catalog() -> dict[str, Any]:
    return {
        "module": "data_management",
        "entities": MANAGED_ENTITIES,
        "audit_table": "fsi.svc_wf_audit_log",
    }


@router.get("/availability", summary="持仓/行情最近可用日")
async def data_management_availability(
    fund_id: str | None = None,
    as_of_date: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cutoff = as_of_date or date.today()
    position_date = None
    if fund_id:
        position_date = await _latest_holdings_date(db, fund_id, cutoff)
    quote_date = (
        await db.execute(
            text(
                """
                SELECT MAX(price_date)
                FROM fsi.mktdata_quotes
                WHERE price_date <= :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
    ).scalar_one()
    return {
        "requested_date": cutoff.isoformat(),
        "fund_id": fund_id,
        "latest_position_date": position_date.isoformat() if position_date else None,
        "latest_quote_date": quote_date.isoformat() if quote_date else None,
    }


@router.get("/positions/{fund_id}", summary="查询证券级持仓明细")
async def list_positions(
    fund_id: str,
    as_of_date: date,
    search: str | None = None,
    table: str | None = Query(default=None, description="balance_bond / balance_cd / ... / all"),
    limit: int = Query(default=500, ge=1, le=2000),
    fallback: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    table_key = _normalize_position_table(table)
    effective = as_of_date
    items = await _list_security_positions(db, fund_id, effective, search, limit, table_key)
    if fallback and not items:
        latest = await _latest_holdings_date(db, fund_id, as_of_date)
        if latest is not None and latest != as_of_date:
            effective = latest
            items = await _list_security_positions(db, fund_id, effective, search, limit, table_key)
    resolved_table = f"fsi.{table_key}" if table_key else "fsi.balance_bond|cd|deposit|cash|stock|fund|repo"
    return {
        "items": items,
        "count": len(items),
        "requested_date": as_of_date.isoformat(),
        "effective_date": effective.isoformat(),
        "table": resolved_table,
        "selected_table": table_key or "all",
    }


@router.post("/positions/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_position(
    fund_id: str,
    as_of_date: date,
    payload: PositionCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    asset_class = str(values["asset_class"]).upper()
    code = values["subject_code"]
    name = values["subject_name"]
    currency = values["currency"]
    quantity = values.get("quantity")
    unit_price = values.get("unit_price")
    cost = values.get("cost")
    market_value = values.get("market_value")
    weight_pct = values.get("weight_pct")
    maturity_date = values.get("maturity_date")
    issuer_name = values.get("issuer_name")
    params = {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "code": code,
        "name": name,
        "currency": currency,
        "quantity": quantity,
        "cost": cost,
        "unit_price": unit_price,
        "market_value": market_value,
        "weight_pct": weight_pct,
        "maturity_date": maturity_date,
        "issuer_name": issuer_name,
    }
    try:
        if asset_class == "BOND":
            if quantity is None or market_value is None:
                raise HTTPException(status_code=422, detail="BOND requires quantity and market_value")
            await db.execute(text("""
                INSERT INTO fsi.balance_bond
                    (evaluate_date, port_id, security_code, security_name, currency,
                     quantity, cost, dirty_price, market_value, weight_pct,
                     maturity_date, issuer_name)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, :currency,
                     :quantity, :cost, :unit_price, :market_value, :weight_pct,
                     :maturity_date, :issuer_name)
            """), params)
        elif asset_class == "CD":
            if quantity is None or market_value is None:
                raise HTTPException(status_code=422, detail="CD requires quantity and market_value")
            await db.execute(text("""
                INSERT INTO fsi.balance_cd
                    (evaluate_date, port_id, security_code, security_name, currency,
                     quantity, cost, price, market_value, weight_pct,
                     maturity_date, issuer_name)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, :currency,
                     :quantity, :cost, :unit_price, :market_value, :weight_pct,
                     :maturity_date, :issuer_name)
            """), params)
        elif asset_class == "DEPOSIT":
            if market_value is None or maturity_date is None:
                raise HTTPException(status_code=422, detail="DEPOSIT requires market_value and maturity_date")
            await db.execute(text("""
                INSERT INTO fsi.balance_deposit
                    (evaluate_date, port_id, deposit_id, deposit_name, currency,
                     value_date, maturity_date, principal, interest_rate,
                     total_value, weight_pct, bank_name)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, :currency,
                     :as_of_date, :maturity_date, :market_value, 0,
                     :market_value, :weight_pct, :issuer_name)
            """), params)
        elif asset_class == "CASH":
            if market_value is None:
                raise HTTPException(status_code=422, detail="CASH requires market_value")
            await db.execute(text("""
                INSERT INTO fsi.balance_cash
                    (evaluate_date, port_id, cash_account_id, account_name, currency,
                     amount, weight_pct, bank_id)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, :currency,
                     :market_value, :weight_pct, :issuer_name)
            """), params)
        elif asset_class == "STOCK":
            if quantity is None or market_value is None:
                raise HTTPException(status_code=422, detail="STOCK requires quantity and market_value")
            await db.execute(text("""
                INSERT INTO fsi.balance_stock
                    (evaluate_date, port_id, security_code, security_name, market_id,
                     currency, quantity, cost, price, market_value, weight_pct, sector)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, 'HKEX',
                     :currency, :quantity, :cost, :unit_price, :market_value, :weight_pct, :issuer_name)
            """), params)
        elif asset_class == "FUND":
            if quantity is None or market_value is None:
                raise HTTPException(status_code=422, detail="FUND requires quantity and market_value")
            await db.execute(text("""
                INSERT INTO fsi.balance_fund
                    (evaluate_date, port_id, security_code, security_name, currency,
                     quantity, cost, market_value, weight_pct)
                VALUES
                    (:as_of_date, :fund_id, :code, :name, :currency,
                     :quantity, :cost, :market_value, :weight_pct)
            """), params)
        elif asset_class == "REPO":
            if market_value is None or maturity_date is None:
                raise HTTPException(status_code=422, detail="REPO requires market_value and maturity_date")
            await db.execute(text("""
                INSERT INTO fsi.balance_repo
                    (evaluate_date, port_id, repo_id, repo_type, currency,
                     value_date, maturity_date, principal, interest_rate,
                     total_value, weight_pct, counterparty_name, pledged_security_name)
                VALUES
                    (:as_of_date, :fund_id, :code, 'REV_REPO', :currency,
                     :as_of_date, :maturity_date, :market_value, 0,
                     :market_value, :weight_pct, :issuer_name, :name)
            """), params)
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported asset_class: {asset_class}")

        await _audit(
            db,
            event_type="POSITION_CREATED",
            actor=actor,
            port_id=fund_id,
            details={"as_of_date": as_of_date, "asset_class": asset_class, "position": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Position already exists") from exc
    return await _get_position(db, fund_id, as_of_date, code, asset_class)


@router.patch("/positions/{fund_id}/{subject_code}")
async def update_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    payload: PositionUpdate,
    actor: str = Query(min_length=1, max_length=128),
    asset_class: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_position(db, fund_id, as_of_date, subject_code, asset_class or payload.asset_class)
    resolved_class = str(previous.get("asset_class") or asset_class or "BOND").upper()
    values = payload.model_dump(exclude_unset=True)
    values.pop("asset_class", None)
    values.pop("data_source", None)
    values.pop("memo", None)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    if "market_value" not in values and ({"quantity", "unit_price"} & values.keys()):
        quantity = values.get("quantity", previous.get("quantity"))
        unit_price = values.get("unit_price", previous.get("unit_price"))
        if quantity is not None and unit_price is not None:
            values["market_value"] = quantity * unit_price

    field_maps = {
        "BOND": {
            "subject_name": "security_name", "currency": "currency", "quantity": "quantity",
            "unit_price": "dirty_price", "cost": "cost", "market_value": "market_value",
            "weight_pct": "weight_pct", "maturity_date": "maturity_date", "issuer_name": "issuer_name",
        },
        "CD": {
            "subject_name": "security_name", "currency": "currency", "quantity": "quantity",
            "unit_price": "price", "cost": "cost", "market_value": "market_value",
            "weight_pct": "weight_pct", "maturity_date": "maturity_date", "issuer_name": "issuer_name",
        },
        "DEPOSIT": {
            "subject_name": "deposit_name", "currency": "currency", "market_value": "total_value",
            "weight_pct": "weight_pct", "maturity_date": "maturity_date", "issuer_name": "bank_name",
        },
        "CASH": {
            "subject_name": "account_name", "currency": "currency", "market_value": "amount",
            "weight_pct": "weight_pct", "issuer_name": "bank_id",
        },
        "STOCK": {
            "subject_name": "security_name", "currency": "currency", "quantity": "quantity",
            "unit_price": "price", "cost": "cost", "market_value": "market_value",
            "weight_pct": "weight_pct", "issuer_name": "sector",
        },
        "FUND": {
            "subject_name": "security_name", "currency": "currency", "quantity": "quantity",
            "cost": "cost", "market_value": "market_value", "weight_pct": "weight_pct",
        },
        "REPO": {
            "subject_name": "pledged_security_name", "currency": "currency", "market_value": "total_value",
            "weight_pct": "weight_pct", "maturity_date": "maturity_date", "issuer_name": "counterparty_name",
        },
    }
    field_map = field_maps[resolved_class]
    table, key_col = _table_key_for_asset_class(resolved_class)
    mapped = {field_map[k]: v for k, v in values.items() if k in field_map}
    if resolved_class == "DEPOSIT" and "total_value" in mapped:
        mapped["principal"] = mapped["total_value"]
    if resolved_class == "REPO" and "total_value" in mapped:
        mapped["principal"] = mapped["total_value"]
    if not mapped:
        raise HTTPException(status_code=422, detail="No updatable fields for this asset class")
    assignments = ", ".join(f"{column} = :{column}" for column in mapped)
    await db.execute(
        text(
            f"""
            UPDATE {table}
            SET {assignments}, loaded_at = NOW()
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
              AND {key_col} = :subject_code
            """
        ),
        {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "subject_code": subject_code,
            **mapped,
        },
    )
    await _audit(
        db,
        event_type="POSITION_UPDATED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous, "changes": values, "asset_class": resolved_class},
    )
    await db.commit()
    return await _get_position(db, fund_id, as_of_date, subject_code, resolved_class)


@router.delete("/positions/{fund_id}/{subject_code}")
async def delete_position(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    actor: str = Query(min_length=1, max_length=128),
    asset_class: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_position(db, fund_id, as_of_date, subject_code, asset_class)
    resolved_class = str(previous.get("asset_class") or asset_class or "BOND").upper()
    table, key_col = _table_key_for_asset_class(resolved_class)
    await db.execute(
        text(
            f"""
            DELETE FROM {table}
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
              AND {key_col} = :subject_code
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
        details={"before": previous, "asset_class": resolved_class},
    )
    await db.commit()
    return {"message": "Position deleted"}


def _attach_source_table(row: dict[str, Any], table: str) -> dict[str, Any]:
    row["source_table"] = f"fsi.{table}"
    return row


async def _latest_market_date(db: AsyncSession, table: str, cutoff: date) -> date | None:
    date_col = {
        "mktdata_quotes": "price_date",
        "mktdata_index_quotes": "price_date",
        "mktdata_futures_quotes": "price_date",
        "mktdata_fx_rate": "rate_date",
        "mktdata_fund_nav": "nav_date",
        "mktdata_security_quotes": "quote_date",
    }[table]
    return (
        await db.execute(
            text(f"SELECT MAX({date_col}) FROM fsi.{table} WHERE {date_col} <= :cutoff"),
            {"cutoff": cutoff},
        )
    ).scalar_one()


async def _get_market_quote(
    db: AsyncSession,
    price_date: date,
    security_code: str,
    price_type: str,
    table: str = "mktdata_quotes",
) -> dict[str, Any]:
    table = _normalize_market_table(table)
    code = security_code.strip().upper()
    ptype = price_type.strip().upper()
    if table == "mktdata_quotes":
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
                {"price_date": price_date, "security_code": code, "price_type": ptype},
            )
        ).first()
    elif table == "mktdata_index_quotes":
        row = (
            await db.execute(
                text(
                    """
                    SELECT price_date, index_code AS security_code, 'INDEX'::text AS market_id,
                           'CLOSE'::text AS price_type, open_price, high_price, low_price,
                           close_price, prev_close, price_change_pct, volume, turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_index_quotes
                    WHERE price_date = :price_date AND index_code = :security_code
                    """
                ),
                {"price_date": price_date, "security_code": code},
            )
        ).first()
    elif table == "mktdata_futures_quotes":
        row = (
            await db.execute(
                text(
                    """
                    SELECT price_date, contract_code AS security_code, 'FUT'::text AS market_id,
                           'SETTLE'::text AS price_type, open_price, high_price, low_price,
                           COALESCE(close_price, settlement_price) AS close_price,
                           prev_settlement AS prev_close, price_change_pct, volume, turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_futures_quotes
                    WHERE price_date = :price_date AND contract_code = :security_code
                    """
                ),
                {"price_date": price_date, "security_code": code},
            )
        ).first()
    elif table == "mktdata_fx_rate":
        base, _, quote = code.partition("/")
        row = (
            await db.execute(
                text(
                    """
                    SELECT rate_date AS price_date,
                           (base_ccy || '/' || quote_ccy) AS security_code,
                           'FX'::text AS market_id, rate_type AS price_type,
                           NULL::numeric AS open_price, NULL::numeric AS high_price,
                           NULL::numeric AS low_price, mid_rate AS close_price,
                           NULL::numeric AS prev_close, NULL::numeric AS price_change_pct,
                           NULL::bigint AS volume, NULL::numeric AS turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_fx_rate
                    WHERE rate_date = :price_date AND base_ccy = :base AND quote_ccy = :quote
                      AND rate_type = :price_type
                    """
                ),
                {
                    "price_date": price_date,
                    "base": (base or code)[:3].upper(),
                    "quote": (quote or "HKD")[:3].upper(),
                    "price_type": ptype or "SPOT",
                },
            )
        ).first()
    elif table == "mktdata_fund_nav":
        row = (
            await db.execute(
                text(
                    """
                    SELECT nav_date AS price_date, fund_code AS security_code,
                           'FUND'::text AS market_id, 'NAV'::text AS price_type,
                           NULL::numeric AS open_price, NULL::numeric AS high_price,
                           NULL::numeric AS low_price, unit_nav AS close_price,
                           NULL::numeric AS prev_close, day_return AS price_change_pct,
                           NULL::bigint AS volume, NULL::numeric AS turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_fund_nav
                    WHERE nav_date = :price_date AND fund_code = :security_code
                    """
                ),
                {"price_date": price_date, "security_code": code},
            )
        ).first()
    else:  # mktdata_security_quotes
        row = (
            await db.execute(
                text(
                    """
                    SELECT quote_date AS price_date, security_code,
                           COALESCE(market_id, 'UNK') AS market_id,
                           source AS price_type, NULL::numeric AS open_price,
                           NULL::numeric AS high_price, NULL::numeric AS low_price,
                           close_price, NULL::numeric AS prev_close,
                           NULL::numeric AS price_change_pct, volume::bigint AS volume,
                           turnover, source AS data_source, loaded_at
                    FROM fsi.mktdata_security_quotes
                    WHERE quote_date = :price_date AND security_code = :security_code
                      AND source = :price_type
                    """
                ),
                {"price_date": price_date, "security_code": code, "price_type": ptype},
            )
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Market quote not found")
    return _attach_source_table(_row_dict(row), table)


async def _list_market_rows(
    db: AsyncSession,
    *,
    table: str,
    price_date: date,
    search: str | None,
    market_id: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    mid = market_id.strip().upper() if market_id else None
    params: dict[str, Any] = {
        "price_date": price_date,
        "search": pattern,
        "market_id": mid,
        "limit": limit,
    }
    if table == "mktdata_quotes":
        where = """
            WHERE price_date = :price_date
              AND (CAST(:search AS text) IS NULL OR security_code ILIKE CAST(:search AS text))
              AND (CAST(:market_id AS text) IS NULL OR market_id = CAST(:market_id AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_quotes {where}"), params)).scalar_one()
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
    elif table == "mktdata_index_quotes":
        where = """
            WHERE price_date = :price_date
              AND (CAST(:search AS text) IS NULL OR index_code ILIKE CAST(:search AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_index_quotes {where}"), params)).scalar_one()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT price_date, index_code AS security_code, 'INDEX'::text AS market_id,
                           'CLOSE'::text AS price_type, open_price, high_price, low_price,
                           close_price, prev_close, price_change_pct, volume, turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_index_quotes {where}
                    ORDER BY index_code LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    elif table == "mktdata_futures_quotes":
        where = """
            WHERE price_date = :price_date
              AND (CAST(:search AS text) IS NULL OR contract_code ILIKE CAST(:search AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_futures_quotes {where}"), params)).scalar_one()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT price_date, contract_code AS security_code, 'FUT'::text AS market_id,
                           'SETTLE'::text AS price_type, open_price, high_price, low_price,
                           COALESCE(close_price, settlement_price) AS close_price,
                           prev_settlement AS prev_close, price_change_pct, volume, turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_futures_quotes {where}
                    ORDER BY contract_code LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    elif table == "mktdata_fx_rate":
        where = """
            WHERE rate_date = :price_date
              AND (CAST(:search AS text) IS NULL
                   OR (base_ccy || '/' || quote_ccy) ILIKE CAST(:search AS text)
                   OR base_ccy ILIKE CAST(:search AS text)
                   OR quote_ccy ILIKE CAST(:search AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_fx_rate {where}"), params)).scalar_one()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT rate_date AS price_date, (base_ccy || '/' || quote_ccy) AS security_code,
                           'FX'::text AS market_id, rate_type AS price_type,
                           NULL::numeric AS open_price, NULL::numeric AS high_price,
                           NULL::numeric AS low_price, mid_rate AS close_price,
                           NULL::numeric AS prev_close, NULL::numeric AS price_change_pct,
                           NULL::bigint AS volume, NULL::numeric AS turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_fx_rate {where}
                    ORDER BY base_ccy, quote_ccy, rate_type LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    elif table == "mktdata_fund_nav":
        where = """
            WHERE nav_date = :price_date
              AND (CAST(:search AS text) IS NULL OR fund_code ILIKE CAST(:search AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_fund_nav {where}"), params)).scalar_one()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT nav_date AS price_date, fund_code AS security_code,
                           'FUND'::text AS market_id, 'NAV'::text AS price_type,
                           NULL::numeric AS open_price, NULL::numeric AS high_price,
                           NULL::numeric AS low_price, unit_nav AS close_price,
                           NULL::numeric AS prev_close, day_return AS price_change_pct,
                           NULL::bigint AS volume, NULL::numeric AS turnover,
                           data_source, loaded_at
                    FROM fsi.mktdata_fund_nav {where}
                    ORDER BY fund_code LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    else:
        where = """
            WHERE quote_date = :price_date
              AND (CAST(:search AS text) IS NULL OR security_code ILIKE CAST(:search AS text))
              AND (CAST(:market_id AS text) IS NULL OR market_id = CAST(:market_id AS text))
        """
        count = (await db.execute(text(f"SELECT COUNT(*) FROM fsi.mktdata_security_quotes {where}"), params)).scalar_one()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT quote_date AS price_date, security_code,
                           COALESCE(market_id, 'UNK') AS market_id, source AS price_type,
                           NULL::numeric AS open_price, NULL::numeric AS high_price,
                           NULL::numeric AS low_price, close_price,
                           NULL::numeric AS prev_close, NULL::numeric AS price_change_pct,
                           volume::bigint AS volume, turnover, source AS data_source, loaded_at
                    FROM fsi.mktdata_security_quotes {where}
                    ORDER BY security_code, source LIMIT :limit
                    """
                ),
                params,
            )
        ).all()
    return [_attach_source_table(_row_dict(row), table) for row in rows], int(count)


@router.get("/market-quotes", summary="查询市场行情")
async def list_market_quotes(
    price_date: date,
    search: str | None = None,
    market_id: str | None = None,
    table: str | None = Query(default="mktdata_quotes"),
    limit: int = Query(default=200, ge=1, le=1000),
    fallback: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    table_key = _normalize_market_table(table)
    effective = price_date
    if fallback:
        latest = await _latest_market_date(db, table_key, price_date)
        if latest is not None:
            effective = latest
    items, count = await _list_market_rows(
        db,
        table=table_key,
        price_date=effective,
        search=search,
        market_id=market_id,
        limit=limit,
    )
    return {
        "items": items,
        "count": count,
        "requested_date": price_date.isoformat(),
        "effective_date": effective.isoformat(),
        "table": f"fsi.{table_key}",
        "selected_table": table_key,
    }


@router.get("/market-quotes/history/{security_code}", summary="行情时序")
async def market_quote_history(
    security_code: str,
    start: date,
    end: date,
    price_type: str = "CLOSE",
    table: str | None = Query(default="mktdata_quotes"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if start > end:
        raise HTTPException(status_code=422, detail="start must not be later than end")
    table_key = _normalize_market_table(table)
    code = security_code.strip().upper()
    ptype = price_type.strip().upper()
    if table_key == "mktdata_quotes":
        sql = """
            SELECT price_date, security_code, market_id, price_type,
                   close_price, price_change_pct, volume, turnover, data_source
            FROM fsi.mktdata_quotes
            WHERE security_code = :security_code AND price_type = :price_type
              AND price_date BETWEEN :start AND :end
            ORDER BY price_date
        """
        params = {"security_code": code, "price_type": ptype, "start": start, "end": end}
    elif table_key == "mktdata_index_quotes":
        sql = """
            SELECT price_date, index_code AS security_code, 'INDEX'::text AS market_id,
                   'CLOSE'::text AS price_type, close_price, price_change_pct, volume, turnover, data_source
            FROM fsi.mktdata_index_quotes
            WHERE index_code = :security_code AND price_date BETWEEN :start AND :end
            ORDER BY price_date
        """
        params = {"security_code": code, "start": start, "end": end}
    elif table_key == "mktdata_futures_quotes":
        sql = """
            SELECT price_date, contract_code AS security_code, 'FUT'::text AS market_id,
                   'SETTLE'::text AS price_type, COALESCE(close_price, settlement_price) AS close_price,
                   price_change_pct, volume, turnover, data_source
            FROM fsi.mktdata_futures_quotes
            WHERE contract_code = :security_code AND price_date BETWEEN :start AND :end
            ORDER BY price_date
        """
        params = {"security_code": code, "start": start, "end": end}
    elif table_key == "mktdata_fx_rate":
        base, _, quote = code.partition("/")
        sql = """
            SELECT rate_date AS price_date, (base_ccy || '/' || quote_ccy) AS security_code,
                   'FX'::text AS market_id, rate_type AS price_type, mid_rate AS close_price,
                   NULL::numeric AS price_change_pct, NULL::bigint AS volume,
                   NULL::numeric AS turnover, data_source
            FROM fsi.mktdata_fx_rate
            WHERE base_ccy = :base AND quote_ccy = :quote AND rate_type = :price_type
              AND rate_date BETWEEN :start AND :end
            ORDER BY rate_date
        """
        params = {
            "base": (base or code)[:3].upper(),
            "quote": (quote or "HKD")[:3].upper(),
            "price_type": ptype or "SPOT",
            "start": start,
            "end": end,
        }
    elif table_key == "mktdata_fund_nav":
        sql = """
            SELECT nav_date AS price_date, fund_code AS security_code, 'FUND'::text AS market_id,
                   'NAV'::text AS price_type, unit_nav AS close_price, day_return AS price_change_pct,
                   NULL::bigint AS volume, NULL::numeric AS turnover, data_source
            FROM fsi.mktdata_fund_nav
            WHERE fund_code = :security_code AND nav_date BETWEEN :start AND :end
            ORDER BY nav_date
        """
        params = {"security_code": code, "start": start, "end": end}
    else:
        sql = """
            SELECT quote_date AS price_date, security_code, COALESCE(market_id, 'UNK') AS market_id,
                   source AS price_type, close_price, NULL::numeric AS price_change_pct,
                   volume::bigint AS volume, turnover, source AS data_source
            FROM fsi.mktdata_security_quotes
            WHERE security_code = :security_code AND source = :price_type
              AND quote_date BETWEEN :start AND :end
            ORDER BY quote_date
        """
        params = {"security_code": code, "price_type": ptype, "start": start, "end": end}
    rows = (await db.execute(text(sql), params)).all()
    return {
        "items": [_attach_source_table(_row_dict(row), table_key) for row in rows],
        "count": len(rows),
        "table": f"fsi.{table_key}",
        "selected_table": table_key,
    }


@router.post("/market-quotes", status_code=status.HTTP_201_CREATED)
async def create_market_quote(
    payload: MarketQuoteCreate,
    actor: str = Query(min_length=1, max_length=128),
    table: str | None = Query(default="mktdata_quotes"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    table_key = _normalize_market_table(table)
    values = payload.model_dump()
    if payload.prev_close:
        values["price_change_pct"] = (
            (payload.close_price - payload.prev_close) / payload.prev_close * 100
        )
    else:
        values["price_change_pct"] = None
    try:
        if table_key == "mktdata_quotes":
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
        elif table_key == "mktdata_index_quotes":
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.mktdata_index_quotes
                        (price_date, index_code, open_price, high_price, low_price, close_price,
                         prev_close, price_change_pct, volume, turnover, data_source)
                    VALUES
                        (:price_date, :security_code, :open_price, :high_price, :low_price,
                         :close_price, :prev_close, :price_change_pct, :volume, :turnover, :data_source)
                    """
                ),
                values,
            )
        elif table_key == "mktdata_futures_quotes":
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.mktdata_futures_quotes
                        (price_date, contract_code, open_price, high_price, low_price, close_price,
                         settlement_price, prev_settlement, price_change_pct, volume, turnover, data_source)
                    VALUES
                        (:price_date, :security_code, :open_price, :high_price, :low_price, :close_price,
                         :close_price, :prev_close, :price_change_pct, :volume, :turnover, :data_source)
                    """
                ),
                values,
            )
        elif table_key == "mktdata_fx_rate":
            base, _, quote = values["security_code"].partition("/")
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.mktdata_fx_rate
                        (rate_date, base_ccy, quote_ccy, rate_type, mid_rate, data_source)
                    VALUES
                        (:price_date, :base, :quote, :price_type, :close_price, :data_source)
                    """
                ),
                {
                    **values,
                    "base": (base or values["security_code"])[:3].upper(),
                    "quote": (quote or values.get("market_id") or "HKD")[:3].upper(),
                },
            )
        elif table_key == "mktdata_fund_nav":
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.mktdata_fund_nav
                        (nav_date, fund_code, unit_nav, day_return, data_source)
                    VALUES
                        (:price_date, :security_code, :close_price, :price_change_pct, :data_source)
                    """
                ),
                values,
            )
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO fsi.mktdata_security_quotes
                        (quote_date, security_code, market_id, close_price, volume, turnover, source, currency)
                    VALUES
                        (:price_date, :security_code, :market_id, :close_price, :volume, :turnover, :price_type, 'HKD')
                    """
                ),
                values,
            )
        await _audit(
            db,
            event_type="MARKET_QUOTE_CREATED",
            actor=actor,
            port_id=None,
            details={"table": table_key, "quote": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Market quote already exists") from exc
    return await _get_market_quote(
        db, payload.price_date, payload.security_code, payload.price_type, table_key
    )


@router.patch("/market-quotes/{price_date}/{security_code}/{price_type}")
async def update_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    payload: MarketQuoteUpdate,
    actor: str = Query(min_length=1, max_length=128),
    table: str | None = Query(default="mktdata_quotes"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    table_key = _normalize_market_table(table)
    previous = await _get_market_quote(db, price_date, security_code, price_type, table_key)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    merged = {**previous, **values}
    high, low, close = merged.get("high_price"), merged.get("low_price"), merged.get("close_price")
    if high is not None and low is not None and close is not None:
        if high < low or not low <= close <= high:
            raise HTTPException(status_code=422, detail="Invalid OHLC range")
    prev_close = merged.get("prev_close")
    if close is not None:
        values["price_change_pct"] = (
            (close - prev_close) / prev_close * 100 if prev_close else None
        )
    code = security_code.strip().upper()
    ptype = price_type.strip().upper()
    if table_key == "mktdata_quotes":
        assignments = ", ".join(f"{column} = :{column}" for column in values)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_quotes SET {assignments}, loaded_at = NOW()
                WHERE price_date = :price_date AND security_code = :security_code
                  AND price_type = :price_type
                """
            ),
            {"price_date": price_date, "security_code": code, "price_type": ptype, **values},
        )
    elif table_key == "mktdata_index_quotes":
        mapping = {
            "open_price": "open_price",
            "high_price": "high_price",
            "low_price": "low_price",
            "close_price": "close_price",
            "prev_close": "prev_close",
            "price_change_pct": "price_change_pct",
            "volume": "volume",
            "turnover": "turnover",
            "data_source": "data_source",
        }
        mapped = {mapping[k]: v for k, v in values.items() if k in mapping}
        if not mapped:
            raise HTTPException(status_code=422, detail="No supported fields to update")
        assignments = ", ".join(f"{column} = :{column}" for column in mapped)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_index_quotes SET {assignments}, loaded_at = NOW()
                WHERE price_date = :price_date AND index_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code, **mapped},
        )
    elif table_key == "mktdata_futures_quotes":
        mapped = {}
        for key, value in values.items():
            if key == "close_price":
                mapped["close_price"] = value
                mapped["settlement_price"] = value
            elif key == "prev_close":
                mapped["prev_settlement"] = value
            elif key in {"open_price", "high_price", "low_price", "price_change_pct", "volume", "turnover", "data_source"}:
                mapped[key] = value
        if not mapped:
            raise HTTPException(status_code=422, detail="No supported fields to update")
        assignments = ", ".join(f"{column} = :{column}" for column in mapped)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_futures_quotes SET {assignments}, loaded_at = NOW()
                WHERE price_date = :price_date AND contract_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code, **mapped},
        )
    elif table_key == "mktdata_fx_rate":
        base, _, quote = code.partition("/")
        mapped = {}
        if "close_price" in values:
            mapped["mid_rate"] = values["close_price"]
        if "data_source" in values:
            mapped["data_source"] = values["data_source"]
        if not mapped:
            raise HTTPException(status_code=422, detail="No supported fields to update")
        assignments = ", ".join(f"{column} = :{column}" for column in mapped)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_fx_rate SET {assignments}, loaded_at = NOW()
                WHERE rate_date = :price_date AND base_ccy = :base AND quote_ccy = :quote
                  AND rate_type = :price_type
                """
            ),
            {
                "price_date": price_date,
                "base": (base or code)[:3].upper(),
                "quote": (quote or "HKD")[:3].upper(),
                "price_type": ptype or "SPOT",
                **mapped,
            },
        )
    elif table_key == "mktdata_fund_nav":
        mapped = {}
        if "close_price" in values:
            mapped["unit_nav"] = values["close_price"]
        if "price_change_pct" in values:
            mapped["day_return"] = values["price_change_pct"]
        if "data_source" in values:
            mapped["data_source"] = values["data_source"]
        if not mapped:
            raise HTTPException(status_code=422, detail="No supported fields to update")
        assignments = ", ".join(f"{column} = :{column}" for column in mapped)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_fund_nav SET {assignments}, loaded_at = NOW()
                WHERE nav_date = :price_date AND fund_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code, **mapped},
        )
    else:
        mapped = {}
        for key, value in values.items():
            if key == "close_price":
                mapped["close_price"] = value
            elif key == "volume":
                mapped["volume"] = value
            elif key == "turnover":
                mapped["turnover"] = value
            elif key == "market_id":
                mapped["market_id"] = value
        if not mapped:
            raise HTTPException(status_code=422, detail="No supported fields to update")
        assignments = ", ".join(f"{column} = :{column}" for column in mapped)
        await db.execute(
            text(
                f"""
                UPDATE fsi.mktdata_security_quotes SET {assignments}, loaded_at = NOW()
                WHERE quote_date = :price_date AND security_code = :security_code
                  AND source = :price_type
                """
            ),
            {"price_date": price_date, "security_code": code, "price_type": ptype, **mapped},
        )
    await _audit(
        db,
        event_type="MARKET_QUOTE_UPDATED",
        actor=actor,
        port_id=None,
        details={"table": table_key, "before": previous, "changes": values},
    )
    await db.commit()
    return await _get_market_quote(db, price_date, security_code, price_type, table_key)


@router.delete("/market-quotes/{price_date}/{security_code}/{price_type}")
async def delete_market_quote(
    price_date: date,
    security_code: str,
    price_type: str,
    actor: str = Query(min_length=1, max_length=128),
    table: str | None = Query(default="mktdata_quotes"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    table_key = _normalize_market_table(table)
    previous = await _get_market_quote(db, price_date, security_code, price_type, table_key)
    code = security_code.strip().upper()
    ptype = price_type.strip().upper()
    if table_key == "mktdata_quotes":
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_quotes
                WHERE price_date = :price_date AND security_code = :security_code
                  AND price_type = :price_type
                """
            ),
            {"price_date": price_date, "security_code": code, "price_type": ptype},
        )
    elif table_key == "mktdata_index_quotes":
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_index_quotes
                WHERE price_date = :price_date AND index_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code},
        )
    elif table_key == "mktdata_futures_quotes":
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_futures_quotes
                WHERE price_date = :price_date AND contract_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code},
        )
    elif table_key == "mktdata_fx_rate":
        base, _, quote = code.partition("/")
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_fx_rate
                WHERE rate_date = :price_date AND base_ccy = :base AND quote_ccy = :quote
                  AND rate_type = :price_type
                """
            ),
            {
                "price_date": price_date,
                "base": (base or code)[:3].upper(),
                "quote": (quote or "HKD")[:3].upper(),
                "price_type": ptype or "SPOT",
            },
        )
    elif table_key == "mktdata_fund_nav":
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_fund_nav
                WHERE nav_date = :price_date AND fund_code = :security_code
                """
            ),
            {"price_date": price_date, "security_code": code},
        )
    else:
        await db.execute(
            text(
                """
                DELETE FROM fsi.mktdata_security_quotes
                WHERE quote_date = :price_date AND security_code = :security_code
                  AND source = :price_type
                """
            ),
            {"price_date": price_date, "security_code": code, "price_type": ptype},
        )
    await _audit(
        db,
        event_type="MARKET_QUOTE_DELETED",
        actor=actor,
        port_id=None,
        details={"table": table_key, "quote": previous},
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


class ShareClassCreate(BaseModel):
    class_id: str = Field(min_length=1, max_length=32)
    port_id: str = Field(min_length=1, max_length=16)
    class_name: str = Field(min_length=1, max_length=60)
    class_name_en: str | None = Field(default=None, max_length=120)
    currency: str = Field(min_length=3, max_length=3)
    isin: str | None = Field(default=None, max_length=12)
    mgmt_fee_bps: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    inception_date: date | None = None

    @field_validator("class_id", "port_id", "currency")
    @classmethod
    def upper_codes(cls, value: str) -> str:
        return value.strip().upper()


class ShareClassUpdate(BaseModel):
    class_name: str | None = Field(default=None, min_length=1, max_length=60)
    class_name_en: str | None = Field(default=None, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    isin: str | None = Field(default=None, max_length=12)
    mgmt_fee_bps: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    inception_date: date | None = None

    @field_validator("currency")
    @classmethod
    def upper_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class PortfolioManagerCreate(BaseModel):
    port_id: str = Field(min_length=1, max_length=16)
    person_id: str = Field(min_length=1, max_length=16)
    role: str = Field(min_length=1, max_length=32)
    begin_date: date
    end_date: date | None = None
    is_lead: bool = False

    @field_validator("port_id", "person_id", "role")
    @classmethod
    def upper_codes(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioManagerUpdate(BaseModel):
    end_date: date | None = None
    is_lead: bool | None = None


_SHARE_CLASS_COLUMNS = """
    class_id, port_id, class_name, class_name_en, currency, isin,
    mgmt_fee_bps, is_active, inception_date, updated_at
"""


async def _get_share_class(db: AsyncSession, class_id: str) -> dict[str, Any]:
    row = (
        await db.execute(
            text(f"SELECT {_SHARE_CLASS_COLUMNS} FROM fsi.para_share_class WHERE class_id = :cid"),
            {"cid": class_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Share class not found")
    return _row_dict(row)


async def _list_share_classes(db: AsyncSession, search: str | None, include_inactive: bool) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                f"""
                SELECT {_SHARE_CLASS_COLUMNS} FROM fsi.para_share_class
                WHERE (:include_inactive OR is_active = TRUE)
                  AND (CAST(:search AS text) IS NULL
                       OR class_id ILIKE CAST(:search AS text)
                       OR port_id ILIKE CAST(:search AS text)
                       OR class_name ILIKE CAST(:search AS text))
                ORDER BY port_id, class_id
                """
            ),
            {"include_inactive": include_inactive, "search": pattern},
        )
    ).all()
    return [_row_dict(row) for row in rows]


async def _list_portfolio_managers(db: AsyncSession, search: str | None) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                """
                SELECT port_id, person_id, role::text AS role, begin_date, end_date, is_lead
                FROM fsi.para_portfolio_manager
                WHERE CAST(:search AS text) IS NULL
                   OR port_id ILIKE CAST(:search AS text)
                   OR person_id ILIKE CAST(:search AS text)
                   OR role::text ILIKE CAST(:search AS text)
                ORDER BY port_id, begin_date DESC, person_id
                """
            ),
            {"search": pattern},
        )
    ).all()
    return [_row_dict(row) for row in rows]


async def _latest_portfolio_metric_date(
    db: AsyncSession,
    table: str,
    fund_id: str,
    cutoff: date,
) -> date | None:
    return (
        await db.execute(
            text(
                f"""
                SELECT MAX(evaluate_date)
                FROM fsi.{table}
                WHERE port_id = :fund_id AND evaluate_date <= :cutoff
                """
            ),
            {"fund_id": fund_id, "cutoff": cutoff},
        )
    ).scalar_one()


async def _list_valuation_sheet(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    search: str | None,
) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                """
                SELECT evaluate_date, port_id, subject_code, subject_name, currency,
                       quantity, unit_price, cost, market_value, weight_pct,
                       data_source, memo, loaded_at
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fund_id AND evaluate_date = :as_of_date
                  AND (CAST(:search AS text) IS NULL
                       OR subject_code ILIKE CAST(:search AS text)
                       OR subject_name ILIKE CAST(:search AS text))
                ORDER BY subject_code
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, "search": pattern},
        )
    ).all()
    return [_row_dict(row) for row in rows]


async def _list_portfolio_nav(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    search: str | None,
) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                """
                SELECT evaluate_date, port_id, currency, total_asset, total_liability,
                       net_asset, shares_outstanding, unit_nav, acc_unit_nav,
                       day_return, class_id, loaded_at
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fund_id AND evaluate_date = :as_of_date
                  AND (CAST(:search AS text) IS NULL
                       OR currency ILIKE CAST(:search AS text)
                       OR COALESCE(class_id, '') ILIKE CAST(:search AS text))
                ORDER BY currency, class_id NULLS FIRST
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, "search": pattern},
        )
    ).all()
    return [_row_dict(row) for row in rows]


async def _list_portfolio_mmf(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    search: str | None,
) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    rows = (
        await db.execute(
            text(
                """
                SELECT evaluate_date, port_id, income_per_10k, return_rate_7d,
                       nav_deviation, nav_deviation_amount, wam_days, wal_days, loaded_at
                FROM fsi.balance_portfolio_mmf
                WHERE port_id = :fund_id AND evaluate_date = :as_of_date
                  AND (CAST(:search AS text) IS NULL OR port_id ILIKE CAST(:search AS text))
                ORDER BY port_id
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, "search": pattern},
        )
    ).all()
    return [_row_dict(row) for row in rows]


@router.get("/portfolios", summary="组合相关主数据列表")
async def list_portfolios(
    search: str | None = None,
    include_inactive: bool = True,
    table: str | None = Query(default="para_portfolio"),
    fund_id: str | None = None,
    as_of_date: date | None = None,
    fallback: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    table_key = _normalize_portfolio_table(table)
    if table_key == "para_share_class":
        items = await _list_share_classes(db, search, include_inactive)
        return {
            "items": items,
            "count": len(items),
            "table": "fsi.para_share_class",
            "selected_table": table_key,
        }
    if table_key == "para_portfolio_manager":
        items = await _list_portfolio_managers(db, search)
        return {
            "items": items,
            "count": len(items),
            "table": "fsi.para_portfolio_manager",
            "selected_table": table_key,
        }
    if table_key in _PORTFOLIO_DATE_SCOPED:
        if not fund_id or not as_of_date:
            raise HTTPException(status_code=422, detail="fund_id and as_of_date are required for this table")
        effective = as_of_date
        if table_key == "balance_valuation_sheet":
            items = await _list_valuation_sheet(db, fund_id, effective, search)
        elif table_key == "balance_portfolio_nav":
            items = await _list_portfolio_nav(db, fund_id, effective, search)
        else:
            items = await _list_portfolio_mmf(db, fund_id, effective, search)
        if fallback and not items:
            latest = await _latest_portfolio_metric_date(db, table_key, fund_id, as_of_date)
            if latest is not None and latest != as_of_date:
                effective = latest
                if table_key == "balance_valuation_sheet":
                    items = await _list_valuation_sheet(db, fund_id, effective, search)
                elif table_key == "balance_portfolio_nav":
                    items = await _list_portfolio_nav(db, fund_id, effective, search)
                else:
                    items = await _list_portfolio_mmf(db, fund_id, effective, search)
        return {
            "items": items,
            "count": len(items),
            "table": f"fsi.{table_key}",
            "selected_table": table_key,
            "requested_date": as_of_date.isoformat(),
            "effective_date": effective.isoformat(),
        }
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
    return {
        "items": [_row_dict(r) for r in rows],
        "count": len(rows),
        "table": "fsi.para_portfolio",
        "selected_table": table_key,
    }


@router.post("/share-classes", status_code=status.HTTP_201_CREATED)
async def create_share_class(
    payload: ShareClassCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.para_share_class
                    (class_id, port_id, class_name, class_name_en, currency, isin,
                     mgmt_fee_bps, is_active, inception_date)
                VALUES
                    (:class_id, :port_id, :class_name, :class_name_en, :currency, :isin,
                     :mgmt_fee_bps, :is_active, :inception_date)
                """
            ),
            values,
        )
        await _audit(
            db,
            event_type="SHARE_CLASS_CREATED",
            actor=actor,
            port_id=payload.port_id,
            details={"share_class": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Share class already exists") from exc
    return await _get_share_class(db, payload.class_id)


@router.patch("/share-classes/{class_id}")
async def update_share_class(
    class_id: str,
    payload: ShareClassUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    class_id = class_id.strip().upper()
    previous = await _get_share_class(db, class_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.para_share_class SET {assignments}, updated_at = NOW()
            WHERE class_id = :class_id
            """
        ),
        {"class_id": class_id, **values},
    )
    await _audit(
        db,
        event_type="SHARE_CLASS_UPDATED",
        actor=actor,
        port_id=str(previous.get("port_id")),
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_share_class(db, class_id)


@router.delete("/share-classes/{class_id}")
async def delete_share_class(
    class_id: str,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    class_id = class_id.strip().upper()
    previous = await _get_share_class(db, class_id)
    await db.execute(text("DELETE FROM fsi.para_share_class WHERE class_id = :cid"), {"cid": class_id})
    await _audit(
        db,
        event_type="SHARE_CLASS_DELETED",
        actor=actor,
        port_id=str(previous.get("port_id")),
        details={"share_class": previous},
    )
    await db.commit()
    return {"message": "Share class deleted"}


@router.post("/portfolio-managers", status_code=status.HTTP_201_CREATED)
async def create_portfolio_manager(
    payload: PortfolioManagerCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.para_portfolio_manager
                    (port_id, person_id, role, begin_date, end_date, is_lead)
                VALUES
                    (:port_id, :person_id, CAST(:role AS fsi.person_role),
                     :begin_date, :end_date, :is_lead)
                """
            ),
            values,
        )
        await _audit(
            db,
            event_type="PORTFOLIO_MANAGER_CREATED",
            actor=actor,
            port_id=payload.port_id,
            details={"manager": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Portfolio manager record already exists") from exc
    rows = await _list_portfolio_managers(db, payload.port_id)
    match = next(
        (
            row
            for row in rows
            if row["port_id"] == payload.port_id
            and row["person_id"] == payload.person_id
            and str(row["begin_date"]) == str(payload.begin_date)
        ),
        values,
    )
    return match


@router.patch("/portfolio-managers")
async def update_portfolio_manager(
    port_id: str,
    person_id: str,
    role: str,
    begin_date: date,
    payload: PortfolioManagerUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    result = await db.execute(
        text(
            f"""
            UPDATE fsi.para_portfolio_manager SET {assignments}
            WHERE port_id = :port_id AND person_id = :person_id
              AND role = CAST(:role AS fsi.person_role) AND begin_date = :begin_date
            """
        ),
        {
            "port_id": port_id.strip().upper(),
            "person_id": person_id.strip().upper(),
            "role": role.strip().upper(),
            "begin_date": begin_date,
            **values,
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Portfolio manager record not found")
    await _audit(
        db,
        event_type="PORTFOLIO_MANAGER_UPDATED",
        actor=actor,
        port_id=port_id.strip().upper(),
        details={
            "port_id": port_id,
            "person_id": person_id,
            "role": role,
            "begin_date": begin_date,
            "changes": values,
        },
    )
    await db.commit()
    rows = await _list_portfolio_managers(db, port_id)
    return next(
        (
            row
            for row in rows
            if row["person_id"] == person_id.strip().upper()
            and str(row["begin_date"]) == str(begin_date)
        ),
        values,
    )


@router.delete("/portfolio-managers")
async def delete_portfolio_manager(
    port_id: str,
    person_id: str,
    role: str,
    begin_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(
        text(
            """
            DELETE FROM fsi.para_portfolio_manager
            WHERE port_id = :port_id AND person_id = :person_id
              AND role = CAST(:role AS fsi.person_role) AND begin_date = :begin_date
            """
        ),
        {
            "port_id": port_id.strip().upper(),
            "person_id": person_id.strip().upper(),
            "role": role.strip().upper(),
            "begin_date": begin_date,
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Portfolio manager record not found")
    await _audit(
        db,
        event_type="PORTFOLIO_MANAGER_DELETED",
        actor=actor,
        port_id=port_id.strip().upper(),
        details={
            "port_id": port_id,
            "person_id": person_id,
            "role": role,
            "begin_date": begin_date,
        },
    )
    await db.commit()
    return {"message": "Portfolio manager deleted"}


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


# ── Portfolio valuation sheet / NAV / MMF metrics ────────────────

class ValuationSheetCreate(BaseModel):
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
    def derive_market_value(self) -> "ValuationSheetCreate":
        if self.market_value is None:
            if self.quantity is None or self.unit_price is None:
                raise ValueError("market_value or both quantity and unit_price are required")
            self.market_value = self.quantity * self.unit_price
        return self


class ValuationSheetUpdate(BaseModel):
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


class PortfolioNavCreate(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    total_asset: Decimal | None = None
    total_liability: Decimal | None = None
    net_asset: Decimal = Field(ge=0)
    shares_outstanding: Decimal | None = Field(default=None, ge=0)
    unit_nav: Decimal | None = Field(default=None, ge=0)
    acc_unit_nav: Decimal | None = Field(default=None, ge=0)
    day_return: Decimal | None = None
    class_id: str | None = Field(default=None, max_length=32)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("class_id")
    @classmethod
    def normalize_class(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class PortfolioNavUpdate(BaseModel):
    total_asset: Decimal | None = None
    total_liability: Decimal | None = None
    net_asset: Decimal | None = Field(default=None, ge=0)
    shares_outstanding: Decimal | None = Field(default=None, ge=0)
    unit_nav: Decimal | None = Field(default=None, ge=0)
    acc_unit_nav: Decimal | None = Field(default=None, ge=0)
    day_return: Decimal | None = None
    class_id: str | None = Field(default=None, max_length=32)

    @field_validator("class_id")
    @classmethod
    def normalize_class(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class PortfolioMmfCreate(BaseModel):
    income_per_10k: Decimal | None = None
    return_rate_7d: Decimal | None = None
    nav_deviation: Decimal | None = None
    nav_deviation_amount: Decimal | None = None
    wam_days: int | None = Field(default=None, ge=0)
    wal_days: int | None = Field(default=None, ge=0)


class PortfolioMmfUpdate(BaseModel):
    income_per_10k: Decimal | None = None
    return_rate_7d: Decimal | None = None
    nav_deviation: Decimal | None = None
    nav_deviation_amount: Decimal | None = None
    wam_days: int | None = Field(default=None, ge=0)
    wal_days: int | None = Field(default=None, ge=0)


async def _get_valuation_row(
    db: AsyncSession, fund_id: str, as_of_date: date, subject_code: str
) -> dict[str, Any]:
    rows = await _list_valuation_sheet(db, fund_id, as_of_date, subject_code)
    match = next(
        (row for row in rows if str(row["subject_code"]).upper() == subject_code.upper()),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Valuation sheet row not found")
    return match


async def _get_nav_row(
    db: AsyncSession, fund_id: str, as_of_date: date, currency: str
) -> dict[str, Any]:
    rows = await _list_portfolio_nav(db, fund_id, as_of_date, None)
    match = next(
        (row for row in rows if str(row["currency"]).upper() == currency.upper()),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Portfolio NAV row not found")
    return match


async def _get_mmf_row(db: AsyncSession, fund_id: str, as_of_date: date) -> dict[str, Any]:
    rows = await _list_portfolio_mmf(db, fund_id, as_of_date, None)
    if not rows:
        raise HTTPException(status_code=404, detail="Portfolio MMF metrics not found")
    return rows[0]


@router.post("/valuation-sheet/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_valuation_sheet_row(
    fund_id: str,
    as_of_date: date,
    payload: ValuationSheetCreate,
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
                     quantity, unit_price, cost, market_value, weight_pct, data_source, memo)
                VALUES
                    (:as_of_date, :fund_id, :subject_code, :subject_name, :currency,
                     :quantity, :unit_price, :cost, :market_value, :weight_pct, :data_source, :memo)
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, **values},
        )
        await _audit(
            db,
            event_type="VALUATION_SHEET_CREATED",
            actor=actor,
            port_id=fund_id,
            details={"as_of_date": as_of_date, "row": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Valuation sheet row already exists") from exc
    return await _get_valuation_row(db, fund_id, as_of_date, payload.subject_code)


@router.patch("/valuation-sheet/{fund_id}/{subject_code}")
async def update_valuation_sheet_row(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    payload: ValuationSheetUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_valuation_row(db, fund_id, as_of_date, subject_code)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.balance_valuation_sheet SET {assignments}, loaded_at = NOW()
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date AND subject_code = :subject_code
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date, "subject_code": subject_code, **values},
    )
    await _audit(
        db,
        event_type="VALUATION_SHEET_UPDATED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_valuation_row(db, fund_id, as_of_date, subject_code)


@router.delete("/valuation-sheet/{fund_id}/{subject_code}")
async def delete_valuation_sheet_row(
    fund_id: str,
    subject_code: str,
    as_of_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_valuation_row(db, fund_id, as_of_date, subject_code)
    await db.execute(
        text(
            """
            DELETE FROM fsi.balance_valuation_sheet
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date AND subject_code = :subject_code
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date, "subject_code": subject_code},
    )
    await _audit(
        db,
        event_type="VALUATION_SHEET_DELETED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous},
    )
    await db.commit()
    return {"message": "Valuation sheet row deleted"}


@router.post("/portfolio-nav/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_portfolio_nav(
    fund_id: str,
    as_of_date: date,
    payload: PortfolioNavCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.balance_portfolio_nav
                    (evaluate_date, port_id, currency, total_asset, total_liability, net_asset,
                     shares_outstanding, unit_nav, acc_unit_nav, day_return, class_id)
                VALUES
                    (:as_of_date, :fund_id, :currency, :total_asset, :total_liability, :net_asset,
                     :shares_outstanding, :unit_nav, :acc_unit_nav, :day_return, :class_id)
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, **values},
        )
        await _audit(
            db,
            event_type="PORTFOLIO_NAV_CREATED",
            actor=actor,
            port_id=fund_id,
            details={"as_of_date": as_of_date, "nav": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Portfolio NAV already exists") from exc
    return await _get_nav_row(db, fund_id, as_of_date, payload.currency)


@router.patch("/portfolio-nav/{fund_id}/{currency}")
async def update_portfolio_nav(
    fund_id: str,
    currency: str,
    as_of_date: date,
    payload: PortfolioNavUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_nav_row(db, fund_id, as_of_date, currency)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.balance_portfolio_nav SET {assignments}, loaded_at = NOW()
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date AND currency = :currency
            """
        ),
        {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "currency": currency.strip().upper(),
            **values,
        },
    )
    await _audit(
        db,
        event_type="PORTFOLIO_NAV_UPDATED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_nav_row(db, fund_id, as_of_date, currency)


@router.delete("/portfolio-nav/{fund_id}/{currency}")
async def delete_portfolio_nav(
    fund_id: str,
    currency: str,
    as_of_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_nav_row(db, fund_id, as_of_date, currency)
    await db.execute(
        text(
            """
            DELETE FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date AND currency = :currency
            """
        ),
        {
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "currency": currency.strip().upper(),
        },
    )
    await _audit(
        db,
        event_type="PORTFOLIO_NAV_DELETED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous},
    )
    await db.commit()
    return {"message": "Portfolio NAV deleted"}


@router.post("/portfolio-mmf/{fund_id}", status_code=status.HTTP_201_CREATED)
async def create_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    payload: PortfolioMmfCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.balance_portfolio_mmf
                    (evaluate_date, port_id, income_per_10k, return_rate_7d, nav_deviation,
                     nav_deviation_amount, wam_days, wal_days)
                VALUES
                    (:as_of_date, :fund_id, :income_per_10k, :return_rate_7d, :nav_deviation,
                     :nav_deviation_amount, :wam_days, :wal_days)
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date, **values},
        )
        await _audit(
            db,
            event_type="PORTFOLIO_MMF_CREATED",
            actor=actor,
            port_id=fund_id,
            details={"as_of_date": as_of_date, "mmf": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Portfolio MMF metrics already exist") from exc
    return await _get_mmf_row(db, fund_id, as_of_date)


@router.patch("/portfolio-mmf/{fund_id}")
async def update_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    payload: PortfolioMmfUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    previous = await _get_mmf_row(db, fund_id, as_of_date)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="No fields to update")
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    await db.execute(
        text(
            f"""
            UPDATE fsi.balance_portfolio_mmf SET {assignments}, loaded_at = NOW()
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date, **values},
    )
    await _audit(
        db,
        event_type="PORTFOLIO_MMF_UPDATED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous, "changes": values},
    )
    await db.commit()
    return await _get_mmf_row(db, fund_id, as_of_date)


@router.delete("/portfolio-mmf/{fund_id}")
async def delete_portfolio_mmf(
    fund_id: str,
    as_of_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    previous = await _get_mmf_row(db, fund_id, as_of_date)
    await db.execute(
        text(
            """
            DELETE FROM fsi.balance_portfolio_mmf
            WHERE port_id = :fund_id AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    await _audit(
        db,
        event_type="PORTFOLIO_MMF_DELETED",
        actor=actor,
        port_id=fund_id,
        details={"before": previous},
    )
    await db.commit()
    return {"message": "Portfolio MMF metrics deleted"}
