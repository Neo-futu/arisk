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


@dataclass(frozen=True)
class HistoricalAssetSeries:
    """Auditable base-currency price path for one current holding."""

    security_code: str
    security_name: str
    asset_class: str
    observations: tuple[tuple[date, float], ...]
    source: str
    treatment: str
    is_real_market: bool


@dataclass(frozen=True)
class HistoricalMarketData:
    """Historical price paths used by current-holdings return backtests."""

    start_date: date
    end_date: date
    series: tuple[HistoricalAssetSeries, ...]
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


def _business_dates(start_date: date, end_date: date) -> list[date]:
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    if not dates:
        dates = [start_date, end_date] if start_date != end_date else [start_date]
    return sorted(set(dates))


def _add_level(
    target: dict[str, list[tuple[date, float]]],
    security_code: Any,
    observation_date: Any,
    level: Any,
) -> None:
    parsed_date = date_value(observation_date)
    parsed_level = number(level)
    if parsed_date is None or parsed_level <= 0.0:
        return
    target.setdefault(str(security_code), []).append((parsed_date, parsed_level))


def _usable(values: list[tuple[date, float]] | None) -> list[tuple[date, float]] | None:
    if not values:
        return None
    deduplicated = sorted(dict(values).items())
    return deduplicated if len(deduplicated) >= 2 else None


async def _mapping_rows(
    db: AsyncSession,
    statement: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    result = await db.execute(text(statement), params)
    return [dict(row) for row in result.mappings().all()]


async def load_historical_market_data(
    fund_id: str,
    positions: list[Position],
    start_date: date,
    end_date: date,
    reporting_currency: str,
    db: AsyncSession,
) -> HistoricalMarketData:
    """Load real market histories for current holdings, with explicit non-market fallbacks."""

    if start_date >= end_date:
        raise ValueError("Historical backtest start_date must be earlier than as_of_date")
    query_start = start_date - timedelta(days=14)
    codes = sorted({position.security_code for position in positions})
    market_quotes: dict[str, list[tuple[date, float]]] = {}
    fund_navs: dict[str, list[tuple[date, float]]] = {}
    bond_prices: dict[str, list[tuple[date, float]]] = {}
    historical_valuations: dict[str, list[tuple[date, float]]] = {}

    if codes:
        for row in await _mapping_rows(
            db,
            """
            SELECT security_code, price_date, close_price
            FROM fsi.mktdata_quotes
            WHERE security_code = ANY(:codes)
              AND price_type = 'CLOSE'
              AND price_date BETWEEN :query_start AND :end_date
            ORDER BY security_code, price_date
            """,
            {"codes": codes, "query_start": query_start, "end_date": end_date},
        ):
            _add_level(market_quotes, row["security_code"], row["price_date"], row["close_price"])

        for row in await _mapping_rows(
            db,
            """
            SELECT fund_code AS security_code, nav_date AS price_date,
                   COALESCE(acc_unit_nav, unit_nav) AS close_price
            FROM fsi.mktdata_fund_nav
            WHERE fund_code = ANY(:codes)
              AND nav_date BETWEEN :query_start AND :end_date
            ORDER BY fund_code, nav_date
            """,
            {"codes": codes, "query_start": query_start, "end_date": end_date},
        ):
            _add_level(fund_navs, row["security_code"], row["price_date"], row["close_price"])

        for row in await _mapping_rows(
            db,
            """
            SELECT internal_id AS security_code, price_date,
                   COALESCE(dirty_price, clean_price) AS close_price
            FROM fsi.mktdata_bond_risk
            WHERE internal_id = ANY(:codes)
              AND price_date BETWEEN :query_start AND :end_date
            ORDER BY internal_id, price_date
            """,
            {"codes": codes, "query_start": query_start, "end_date": end_date},
        ):
            _add_level(bond_prices, row["security_code"], row["price_date"], row["close_price"])

        valuation_queries = (
            """SELECT security_code, evaluate_date AS price_date,
                      COALESCE(price, market_value / NULLIF(quantity, 0)) AS close_price
                 FROM fsi.balance_stock
                WHERE port_id = :fund_id AND security_code = ANY(:codes)
                  AND evaluate_date BETWEEN :query_start AND :end_date""",
            """SELECT security_code, evaluate_date AS price_date,
                      COALESCE(unit_nav, market_value / NULLIF(quantity, 0)) AS close_price
                 FROM fsi.balance_fund
                WHERE port_id = :fund_id AND security_code = ANY(:codes)
                  AND evaluate_date BETWEEN :query_start AND :end_date""",
            """SELECT security_code, evaluate_date AS price_date,
                      COALESCE(dirty_price, clean_price, market_value / NULLIF(quantity, 0)) AS close_price
                 FROM fsi.balance_bond
                WHERE port_id = :fund_id AND security_code = ANY(:codes)
                  AND evaluate_date BETWEEN :query_start AND :end_date""",
            """SELECT security_code, evaluate_date AS price_date,
                      COALESCE(price, market_value / NULLIF(quantity, 0)) AS close_price
                 FROM fsi.balance_cd
                WHERE port_id = :fund_id AND security_code = ANY(:codes)
                  AND evaluate_date BETWEEN :query_start AND :end_date""",
            """SELECT deposit_id AS security_code, evaluate_date AS price_date,
                      COALESCE(total_value / NULLIF(principal, 0), 1.0) AS close_price
                 FROM fsi.balance_deposit
                WHERE port_id = :fund_id AND deposit_id = ANY(:codes)
                  AND evaluate_date BETWEEN :query_start AND :end_date""",
        )
        valuation_params = {
            "fund_id": fund_id,
            "codes": codes,
            "query_start": query_start,
            "end_date": end_date,
        }
        for statement in valuation_queries:
            for row in await _mapping_rows(db, statement, valuation_params):
                _add_level(
                    historical_valuations,
                    row["security_code"],
                    row["price_date"],
                    row["close_price"],
                )

    currencies = sorted({
        position.currency
        for position in positions
        if position.currency and position.currency != reporting_currency
    })
    fx_levels: dict[str, list[tuple[date, float]]] = {}
    if currencies:
        fx_rows = await _mapping_rows(
            db,
            """
            SELECT rate_date, base_ccy, quote_ccy, mid_rate
            FROM fsi.mktdata_fx_rate
            WHERE rate_type = 'SPOT'
              AND rate_date BETWEEN :query_start AND :end_date
              AND ((base_ccy = ANY(:currencies) AND quote_ccy = :reporting_currency)
                OR (base_ccy = :reporting_currency AND quote_ccy = ANY(:currencies)))
            ORDER BY rate_date
            """,
            {
                "currencies": currencies,
                "reporting_currency": reporting_currency,
                "query_start": query_start,
                "end_date": end_date,
            },
        )
        for row in fx_rows:
            base = str(row["base_ccy"])
            quote = str(row["quote_ccy"])
            rate = number(row["mid_rate"])
            if rate <= 0.0:
                continue
            currency = base if quote == reporting_currency else quote
            converted = rate if quote == reporting_currency else 1.0 / rate
            _add_level(fx_levels, currency, row["rate_date"], converted)

    calendar = _business_dates(start_date, end_date)
    output: list[HistoricalAssetSeries] = []
    used_sources: set[str] = set()
    for position in positions:
        code = position.security_code
        source = ""
        treatment = ""
        real_market = False
        selected: list[tuple[date, float]] | None = None
        if position.asset_class in {"BOND", "CD"}:
            selected = _usable(bond_prices.get(code))
            if selected:
                source = "fsi.mktdata_bond_risk"
        elif position.asset_class == "FUND":
            selected = _usable(fund_navs.get(code))
            if selected:
                source = "fsi.mktdata_fund_nav"
            else:
                selected = _usable(market_quotes.get(code))
                if selected:
                    source = "fsi.mktdata_quotes"
        elif position.asset_class == "EQUITY":
            selected = _usable(market_quotes.get(code))
            if selected:
                source = "fsi.mktdata_quotes"

        if selected:
            treatment = "REAL_MARKET"
            real_market = True
        else:
            selected = _usable(historical_valuations.get(code))
            if selected:
                source = "fsi.balance_*"
                treatment = "HISTORICAL_VALUATION"
            else:
                annual_rate = position.ytm or position.coupon_rate
                if abs(annual_rate) > 1.0:
                    annual_rate /= 100.0
                if position.asset_class in {"BOND", "CD", "DEPOSIT"} and annual_rate > -1.0:
                    selected = [
                        (item, (1.0 + annual_rate) ** ((item - start_date).days / 365.0))
                        for item in calendar
                    ]
                    source = "position.ytm/coupon_rate"
                    treatment = "ACCRUAL_PROXY"
                else:
                    selected = [(item, 1.0) for item in calendar]
                    source = "constant_value"
                    treatment = "ZERO_RETURN_PROXY"

        if position.currency != reporting_currency:
            fx_path = _usable(fx_levels.get(position.currency))
            latest_fx = position.fx_rate or 1.0
            fx_index = 0
            converted: list[tuple[date, float]] = []
            for observation_date, level in selected:
                while fx_path and fx_index < len(fx_path) and fx_path[fx_index][0] <= observation_date:
                    latest_fx = fx_path[fx_index][1]
                    fx_index += 1
                converted.append((observation_date, level * latest_fx))
            selected = converted
            if fx_path:
                source = f"{source}+fsi.mktdata_fx_rate"
            else:
                treatment = f"{treatment}_STATIC_FX"

        used_sources.update(source.split("+"))
        output.append(HistoricalAssetSeries(
            security_code=code,
            security_name=position.security_name,
            asset_class=position.asset_class,
            observations=tuple(selected),
            source=source,
            treatment=treatment,
            is_real_market=real_market,
        ))

    return HistoricalMarketData(
        start_date=start_date,
        end_date=end_date,
        series=tuple(output),
        source_tables=tuple(sorted(item for item in used_sources if item)),
    )
