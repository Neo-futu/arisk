"""Risk input orchestration over modular portfolio and market adapters."""
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from .market_data import enrich_positions, load_market_data, market_quality
from .models import PortfolioSnapshot
from .portfolio_data import load_portfolio_header, load_positions, reconcile_to_nav


async def load_portfolio_snapshot(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    lookback_days: int = 500,
) -> PortfolioSnapshot:
    """Compose existing ARISK portfolio and market inputs into one risk snapshot."""

    header = await load_portfolio_header(fund_id, as_of_date, db)
    source_positions = await load_positions(fund_id, header, db)
    market = await load_market_data(
        fund_id,
        header.effective_date,
        source_positions,
        lookback_days,
        db,
    )
    enriched_positions = enrich_positions(source_positions, market)
    positions, portfolio_quality = reconcile_to_nav(enriched_positions, header)
    return PortfolioSnapshot(
        fund_id=fund_id,
        as_of_date=header.effective_date,
        reporting_currency=header.reporting_currency,
        net_asset=header.net_asset,
        positions=positions,
        nav_returns=market.nav_returns,
        data_quality={
            **portfolio_quality,
            **market_quality(market),
            "input_orchestrator": "risk_testing.loader.load_portfolio_snapshot",
        },
    )
