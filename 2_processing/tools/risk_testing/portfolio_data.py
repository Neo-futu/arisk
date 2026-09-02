"""Portfolio holding adapter using existing ARISK authoritative tables."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Position


@dataclass(frozen=True)
class PortfolioHeader:
    """Latest authorized portfolio valuation header."""

    requested_date: date
    effective_date: date
    reporting_currency: str
    net_asset: float


def number(value: Any, default: float = 0.0) -> float:
    """Convert database numerics to finite Python floats."""

    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def date_value(value: Any) -> date | None:
    """Convert a database date-like value to ``date``."""

    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


async def rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute a mapping query against an existing ARISK table."""

    result = await db.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def load_portfolio_header(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> PortfolioHeader:
    """Load NAV, reporting currency and effective date from existing portfolio data."""

    records = await rows(
        db,
        """
        SELECT evaluate_date, currency, net_asset
        FROM fsi.balance_portfolio_nav
        WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
        ORDER BY evaluate_date DESC
        LIMIT 1
        """,
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    if not records:
        raise ValueError("No portfolio NAV found on or before the requested date")
    record = records[0]
    effective_date = date_value(record["evaluate_date"]) or as_of_date
    return PortfolioHeader(
        requested_date=as_of_date,
        effective_date=effective_date,
        reporting_currency=str(record.get("currency") or "HKD"),
        net_asset=number(record.get("net_asset")),
    )


async def load_positions(
    fund_id: str,
    header: PortfolioHeader,
    db: AsyncSession,
) -> list[Position]:
    """Normalize bonds, CDs, deposits, equities, funds and cash into positions."""

    params = {"fund_id": fund_id, "effective_date": header.effective_date}
    common_date = (
        "evaluate_date = (SELECT MAX(evaluate_date) FROM {table} "
        "WHERE port_id = :fund_id AND evaluate_date <= :effective_date)"
    )
    bond_rows = await rows(db, f"""
        SELECT security_code, security_name, 'BOND' AS asset_class, currency,
               market_value, COALESCE(market_value_base, market_value) AS market_value_base,
               COALESCE(duration, 0) AS duration, COALESCE(convexity, 0) AS convexity,
               COALESCE(ytm, 0) AS ytm, COALESCE(coupon_rate, 0) AS coupon_rate,
               maturity_date, COALESCE(fx_rate, 1) AS fx_rate,
               COALESCE(debt_rating, issuer_rating, 'NR') AS rating,
               COALESCE(issuer_name, 'UNKNOWN') AS issuer
        FROM fsi.balance_bond WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_bond')}
    """, params)
    cd_rows = await rows(db, f"""
        SELECT security_code, security_name, 'CD' AS asset_class, currency,
               market_value, COALESCE(market_value_base, market_value) AS market_value_base,
               COALESCE(duration, 0) AS duration, COALESCE(convexity, 0) AS convexity,
               COALESCE(ytm, 0) AS ytm, COALESCE(coupon_rate, 0) AS coupon_rate,
               maturity_date, COALESCE(fx_rate, 1) AS fx_rate,
               COALESCE(issuer_rating, 'NR') AS rating,
               COALESCE(issuer_name, 'UNKNOWN') AS issuer
        FROM fsi.balance_cd WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_cd')}
    """, params)
    deposit_rows = await rows(db, f"""
        SELECT deposit_id AS security_code, COALESCE(deposit_name, deposit_id) AS security_name,
               'DEPOSIT' AS asset_class, currency, COALESCE(total_value, principal) AS market_value,
               COALESCE(total_value_base, total_value, principal) AS market_value_base,
               GREATEST((maturity_date - evaluate_date)::numeric / 365.0, 0) AS duration,
               0 AS convexity, COALESCE(interest_rate, 0) AS ytm,
               COALESCE(interest_rate, 0) AS coupon_rate, maturity_date,
               COALESCE(fx_rate, 1) AS fx_rate, COALESCE(bank_rating, 'NR') AS rating,
               COALESCE(bank_name, 'UNKNOWN') AS issuer
        FROM fsi.balance_deposit WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_deposit')}
    """, params)
    stock_rows = await rows(db, f"""
        SELECT security_code, security_name, 'EQUITY' AS asset_class, currency,
               market_value, COALESCE(market_value_base, market_value) AS market_value_base,
               0 AS duration, 0 AS convexity, 0 AS ytm, 0 AS coupon_rate,
               NULL AS maturity_date, COALESCE(fx_rate, 1) AS fx_rate,
               NULL AS rating, COALESCE(sector, 'UNKNOWN') AS issuer
        FROM fsi.balance_stock WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_stock')}
    """, params)
    fund_rows = await rows(db, f"""
        SELECT security_code, security_name, 'FUND' AS asset_class, currency,
               market_value, COALESCE(market_value_base, market_value) AS market_value_base,
               0 AS duration, 0 AS convexity, 0 AS ytm, 0 AS coupon_rate,
               NULL AS maturity_date, COALESCE(fx_rate, 1) AS fx_rate,
               NULL AS rating, COALESCE(fund_type, 'FUND') AS issuer
        FROM fsi.balance_fund WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_fund')}
    """, params)
    cash_rows = await rows(db, f"""
        SELECT cash_account_id AS security_code, COALESCE(account_name, cash_account_id) AS security_name,
               'CASH' AS asset_class, currency, amount AS market_value,
               COALESCE(amount_base_ccy, amount) AS market_value_base,
               0 AS duration, 0 AS convexity, 0 AS ytm, 0 AS coupon_rate,
               NULL AS maturity_date, COALESCE(fx_rate, 1) AS fx_rate,
               NULL AS rating, COALESCE(bank_id, 'CASH') AS issuer
        FROM fsi.balance_cash WHERE port_id = :fund_id AND {common_date.format(table='fsi.balance_cash')}
    """, params)

    positions: list[Position] = []
    for record in bond_rows + cd_rows + deposit_rows + stock_rows + fund_rows + cash_rows:
        market_value = number(record.get("market_value"))
        market_value_base = number(record.get("market_value_base"), market_value)
        positions.append(Position(
            security_code=str(record.get("security_code") or "UNKNOWN"),
            security_name=str(record.get("security_name") or record.get("security_code") or "UNKNOWN"),
            asset_class=str(record.get("asset_class") or "OTHER"),
            currency=str(record.get("currency") or header.reporting_currency),
            market_value=market_value,
            market_value_base=market_value_base,
            duration=max(number(record.get("duration")), 0.0),
            convexity=max(number(record.get("convexity")), 0.0),
            ytm=number(record.get("ytm")),
            coupon_rate=number(record.get("coupon_rate")),
            maturity_date=date_value(record.get("maturity_date")),
            fx_rate=number(record.get("fx_rate"), 1.0) or 1.0,
            metadata={"rating": record.get("rating"), "issuer": record.get("issuer")},
        ))
    return positions


def reconcile_to_nav(
    positions: list[Position],
    header: PortfolioHeader,
) -> tuple[list[Position], dict[str, Any]]:
    """Reconcile PV to NAV while preserving transparent source-risk coverage."""

    reconciled = list(positions)
    covered_value = sum(item.market_value_base for item in positions)
    unmapped_balance = header.net_asset - covered_value
    threshold = max(abs(header.net_asset) * 1e-8, 0.01)
    has_residual = unmapped_balance > threshold
    if has_residual:
        reconciled.append(Position(
            security_code="UNMAPPED_NAV",
            security_name="未映射净资产（风险中性待分类）",
            asset_class="UNMAPPED_CASH",
            currency=header.reporting_currency,
            market_value=unmapped_balance,
            market_value_base=unmapped_balance,
            metadata={"model_treatment": "risk-neutral residual", "requires_mapping": True},
        ))
    quality = {
        "requested_date": header.requested_date.isoformat(),
        "effective_date": header.effective_date.isoformat(),
        "position_count": len(reconciled),
        "source_position_count": len(positions),
        "source_risk_coverage_pct": covered_value / header.net_asset * 100.0 if header.net_asset else None,
        "unmapped_balance": max(unmapped_balance, 0.0),
        "valuation_coverage_pct": (
            (covered_value + max(unmapped_balance, 0.0)) / header.net_asset * 100.0
            if header.net_asset else None
        ),
        "portfolio_source": "ARISK fsi.balance_* authoritative holding tables",
    }
    return reconciled, quality
