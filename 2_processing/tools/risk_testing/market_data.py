"""Market-data adapter using existing ARISK NAV and quote histories."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Position
from .portfolio_data import date_value, number


@dataclass(frozen=True)
class MarketDataSnapshot:
    """Historical return and security-volatility inputs for risk testing."""

    nav_returns: list[tuple[date, float]]
    annualized_volatility: dict[str, float]
    quote_observations: int
    source_tables: tuple[str, ...]


async def load_market_data(
    fund_id: str,
    effective_date: date,
    positions: list[Position],
    lookback_days: int,
    db: AsyncSession,
) -> MarketDataSnapshot:
    """Load NAV returns and held-security quote volatility from existing data."""

    start_date = effective_date - timedelta(days=max(lookback_days * 2, 365))
    nav_result = await db.execute(
        text(
            """
            SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id
              AND evaluate_date BETWEEN :start_date AND :effective_date
              AND COALESCE(acc_unit_nav, unit_nav) IS NOT NULL
            ORDER BY evaluate_date
            """
        ),
        {"fund_id": fund_id, "start_date": start_date, "effective_date": effective_date},
    )
    nav_returns: list[tuple[date, float]] = []
    previous: float | None = None
    for row in nav_result.mappings().all():
        current = number(row.get("nav"))
        observation_date = date_value(row.get("evaluate_date"))
        if observation_date is not None and previous not in (None, 0.0):
            nav_returns.append((observation_date, current / previous - 1.0))
        previous = current
    nav_returns = nav_returns[-lookback_days:]

    security_codes = sorted({position.security_code for position in positions if position.asset_class in {"EQUITY", "FUND"}})
    volatility: dict[str, float] = {}
    quote_observations = 0
    if security_codes:
        quote_result = await db.execute(
            text(
                """
                SELECT security_code, price_date, close_price
                FROM fsi.mktdata_quotes
                WHERE security_code = ANY(:security_codes)
                  AND price_type = 'CLOSE'
                  AND price_date BETWEEN :start_date AND :effective_date
                ORDER BY security_code, price_date
                """
            ),
            {
                "security_codes": security_codes,
                "start_date": start_date,
                "effective_date": effective_date,
            },
        )
        by_security: dict[str, list[float]] = {}
        for row in quote_result.mappings().all():
            by_security.setdefault(str(row["security_code"]), []).append(number(row["close_price"]))
            quote_observations += 1
        for security_code, prices in by_security.items():
            values = np.asarray(prices, dtype=float)
            if values.size >= 3:
                returns = np.diff(values) / values[:-1]
                volatility[security_code] = float(np.std(returns, ddof=1) * np.sqrt(252.0))

    return MarketDataSnapshot(
        nav_returns=nav_returns,
        annualized_volatility=volatility,
        quote_observations=quote_observations,
        source_tables=("fsi.balance_portfolio_nav", "fsi.mktdata_quotes"),
    )


def enrich_positions(
    positions: list[Position],
    market: MarketDataSnapshot,
) -> list[Position]:
    """Attach observed volatility without mutating portfolio identifiers or PV."""

    for position in positions:
        if position.security_code in market.annualized_volatility:
            position.metadata["historical_volatility"] = market.annualized_volatility[position.security_code]
    return positions


def market_quality(market: MarketDataSnapshot) -> dict[str, Any]:
    """Return auditable market-data coverage metadata."""

    return {
        "nav_observations": len(market.nav_returns),
        "quote_observations": market.quote_observations,
        "volatility_security_count": len(market.annualized_volatility),
        "market_data_sources": list(market.source_tables),
    }
