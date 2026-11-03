"""Canonical platform tables consumed by RiskEngine.

RiskEngine does not create a second Portfolio / Position / Market Data store.
Loaders stay on existing ``fsi.balance_*`` / ``fsi.mktdata_*`` adapters.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .asof import DEFAULT_MARKET_FALLBACK, DEFAULT_MARKET_FALLBACK_SOURCE, DEFAULT_MARKET_SOURCE

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
    "fsi.mktdata_index_quotes",
)


async def load_portfolio_snapshot(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    lookback_days: int = 500,
    *,
    market_source: str = DEFAULT_MARKET_SOURCE,
    market_lookback_days: int = 30,
    market_fallback: bool = DEFAULT_MARKET_FALLBACK,
    market_fallback_source: str | None = DEFAULT_MARKET_FALLBACK_SOURCE,
    benchmark_id: str | None = None,
) -> Any:
    """Compose the existing ARISK snapshot: 持仓 + 个券行情 + 指数基准。"""

    from importlib import import_module

    from .asof import attach_market_panel, load_asof_market_panel
    from .index import attach_benchmark, load_benchmark_pack

    loader = import_module("2_processing.tools.risk_testing.loader")
    snapshot = await loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days)
    panel = await load_asof_market_panel(
        db,
        snapshot,
        source=market_source,
        lookback_days=market_lookback_days,
        fallback=market_fallback,
        fallback_source=market_fallback_source,
    )
    attach_market_panel(snapshot, panel)
    pack = await load_benchmark_pack(
        db,
        snapshot,
        lookback_days=lookback_days,
        benchmark_id=benchmark_id,
    )
    attach_benchmark(snapshot, pack)
    return snapshot
