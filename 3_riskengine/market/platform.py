"""Canonical platform tables consumed by RiskEngine.

RiskEngine does not create a second Portfolio / Position / Market Data store.
Loaders stay on existing ``fsi.balance_*`` / ``fsi.mktdata_*`` adapters.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

CANONICAL_TABLES = {
    "Market": "fsi.mktdata_*",
    "Portfolio": "fsi.para_portfolio",
    "Position": "fsi.balance_*",
    "Trade": "fsi.transact_*",
    "Valuation": "fsi.balance_valuation_sheet",
    "NAV": "fsi.balance_portfolio_nav",
    "PnL": "fsi.transact_portfolio_pnl",
    "Risk": "fsi.svc_risk_snapshot",
}

HOLDING_TABLES = (
    "fsi.balance_bond",
    "fsi.balance_cd",
    "fsi.balance_deposit",
    "fsi.balance_stock",
    "fsi.balance_fund",
    "fsi.balance_cash",
    "fsi.balance_portfolio_nav",
)

MARKET_TABLES = (
    "fsi.mktdata_quotes",
    "fsi.mktdata_fund_nav",
    "fsi.mktdata_bond_risk",
    "fsi.mktdata_fx_rate",
)


async def load_portfolio_snapshot(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    lookback_days: int = 500,
) -> Any:
    """Compose the existing ARISK snapshot. SQL lives in risk_testing loaders."""

    from importlib import import_module

    loader = import_module("2_processing.tools.risk_testing.loader")
    return await loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days)
