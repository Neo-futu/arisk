"""Security-level portfolio holdings for investment risk indicators."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _number
from .investment_analysis_overview import _latest_snapshot_date


async def _safe_rows(db: AsyncSession, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        result = await db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]
    except ProgrammingError:
        await db.rollback()
        return []


def _serialize_holding(row: dict[str, Any]) -> dict[str, Any]:
    maturity = row.get("maturity_date")
    subtype = row.get("sub_asset_class")
    return {
        "security_code": str(row.get("security_code") or "—"),
        "security_name": str(row.get("security_name") or row.get("security_code") or "—"),
        "asset_class": str(row.get("asset_class") or "OTHER"),
        "sub_asset_class": str(subtype).strip().upper() if subtype else None,
        "currency": str(row.get("currency") or "—"),
        "market_value_base": _number(row.get("market_value_base")),
        "weight_pct": _number(row.get("weight_pct")),
        "quantity": None if row.get("quantity") is None else _number(row.get("quantity")),
        "issuer_name": row.get("issuer_name"),
        "sector": row.get("sector"),
        "rating": row.get("rating"),
        "maturity_date": maturity.isoformat() if hasattr(maturity, "isoformat") else maturity,
        "coupon_rate": None if row.get("coupon_rate") is None else _number(row.get("coupon_rate")),
        "ytm": None if row.get("ytm") is None else _number(row.get("ytm")),
        "duration": None if row.get("duration") is None else _number(row.get("duration")),
        "unrealized_pnl": None if row.get("unrealized_pnl") is None else _number(row.get("unrealized_pnl")),
    }


async def _safe_snapshot_date(
    db: AsyncSession,
    table: str,
    fund_id: str,
    as_of_date: date,
) -> date | None:
    try:
        return await _latest_snapshot_date(db, table, fund_id, as_of_date)
    except ProgrammingError:
        await db.rollback()
        return None


async def compute_security_holdings(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """個券層面完整持倉：整體列表 + 按資產類別分組明細。"""
    stock_date = await _safe_snapshot_date(db, "balance_stock", fund_id, as_of_date)
    bond_date = await _safe_snapshot_date(db, "balance_bond", fund_id, as_of_date)
    cd_date = await _safe_snapshot_date(db, "balance_cd", fund_id, as_of_date)
    deposit_date = await _safe_snapshot_date(db, "balance_deposit", fund_id, as_of_date)
    fund_date = await _safe_snapshot_date(db, "balance_fund", fund_id, as_of_date)
    cash_date = await _safe_snapshot_date(db, "balance_cash", fund_id, as_of_date)
    repo_date = await _safe_snapshot_date(db, "balance_repo", fund_id, as_of_date)

    holdings: list[dict[str, Any]] = []

    if stock_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT security_code, security_name, 'EQUITY' AS asset_class, currency,
                       COALESCE(market_value_base, market_value, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       quantity, NULL::text AS issuer_name,
                       COALESCE(sector, '未分類') AS sector,
                       NULL::text AS rating, NULL::date AS maturity_date,
                       NULL::numeric AS coupon_rate, NULL::numeric AS ytm,
                       NULL::numeric AS duration, unrealized_pnl
                FROM fsi.balance_stock
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, market_value) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": stock_date},
            )
        )

    if bond_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT security_code, security_name, 'BOND' AS asset_class,
                       COALESCE(asset_subtype::text, 'OTHER') AS sub_asset_class,
                       currency,
                       COALESCE(market_value_base, total_market_value, market_value, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       quantity, COALESCE(issuer_name, '—') AS issuer_name,
                       COALESCE(sector, '未分類') AS sector,
                       COALESCE(debt_rating, issuer_rating, internal_rating) AS rating,
                       maturity_date, coupon_rate, ytm, duration, NULL::numeric AS unrealized_pnl
                FROM fsi.balance_bond
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, total_market_value, market_value) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": bond_date},
            )
        )

    if cd_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT security_code, security_name, 'CD' AS asset_class, currency,
                       COALESCE(market_value_base, market_value, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       quantity, COALESCE(issuer_name, '—') AS issuer_name,
                       NULL::text AS sector,
                       COALESCE(issuer_rating, 'NR') AS rating,
                       maturity_date, coupon_rate, ytm, duration, NULL::numeric AS unrealized_pnl
                FROM fsi.balance_cd
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, market_value) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": cd_date},
            )
        )

    if deposit_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT deposit_id AS security_code,
                       COALESCE(deposit_name, deposit_id) AS security_name,
                       'DEPOSIT' AS asset_class, currency,
                       COALESCE(principal, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       NULL::numeric AS quantity,
                       COALESCE(bank_name, '—') AS issuer_name,
                       NULL::text AS sector,
                       NULL::text AS rating,
                       maturity_date,
                       interest_rate AS coupon_rate,
                       interest_rate AS ytm,
                       GREATEST((maturity_date - evaluate_date)::numeric / 365.0, 0) AS duration,
                       NULL::numeric AS unrealized_pnl
                FROM fsi.balance_deposit
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(principal, 0) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": deposit_date},
            )
        )

    if fund_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT security_code, security_name, 'FUND' AS asset_class, currency,
                       COALESCE(market_value_base, market_value, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       quantity, COALESCE(fund_type, 'FUND') AS issuer_name,
                       NULL::text AS sector, NULL::text AS rating,
                       NULL::date AS maturity_date,
                       NULL::numeric AS coupon_rate, NULL::numeric AS ytm,
                       NULL::numeric AS duration, NULL::numeric AS unrealized_pnl
                FROM fsi.balance_fund
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(market_value_base, market_value) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": fund_date},
            )
        )

    if cash_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT cash_account_id AS security_code,
                       COALESCE(account_name, cash_account_id) AS security_name,
                       'CASH' AS asset_class, currency,
                       COALESCE(amount_base_ccy, amount, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       NULL::numeric AS quantity,
                       COALESCE(bank_id, 'CASH') AS issuer_name,
                       NULL::text AS sector, NULL::text AS rating,
                       NULL::date AS maturity_date,
                       NULL::numeric AS coupon_rate, NULL::numeric AS ytm,
                       NULL::numeric AS duration, NULL::numeric AS unrealized_pnl
                FROM fsi.balance_cash
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(amount_base_ccy, amount) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": cash_date},
            )
        )

    if repo_date is not None:
        holdings.extend(
            await _safe_rows(
                db,
                """
                SELECT repo_id AS security_code,
                       COALESCE(counterparty_name, repo_id, 'REPO') AS security_name,
                       'REPO' AS asset_class, currency,
                       COALESCE(principal, 0) AS market_value_base,
                       COALESCE(weight_pct, 0) AS weight_pct,
                       NULL::numeric AS quantity,
                       COALESCE(counterparty_name, '—') AS issuer_name,
                       NULL::text AS sector, NULL::text AS rating,
                       COALESCE(actual_maturity_date, maturity_date) AS maturity_date,
                       interest_rate AS coupon_rate,
                       interest_rate AS ytm,
                       NULL::numeric AS duration, NULL::numeric AS unrealized_pnl
                FROM fsi.balance_repo
                WHERE port_id = :fund_id AND evaluate_date = :snapshot
                ORDER BY COALESCE(principal, 0) DESC NULLS LAST
                """,
                {"fund_id": fund_id, "snapshot": repo_date},
            )
        )

    serialized = [_serialize_holding(row) for row in holdings]
    serialized.sort(
        key=lambda item: (item["weight_pct"] or 0, item["market_value_base"] or 0),
        reverse=True,
    )

    # Fill missing weight_pct from market-value share.
    total_mv = sum(item["market_value_base"] or 0 for item in serialized)
    if total_mv > 0:
        for item in serialized:
            if not item["weight_pct"]:
                item["weight_pct"] = round((item["market_value_base"] or 0) / total_mv * 100.0, 6)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in serialized:
        grouped.setdefault(item["asset_class"], []).append(item)

    by_asset_class = []
    for asset_class, rows in grouped.items():
        by_asset_class.append(
            {
                "asset_class": asset_class,
                "count": len(rows),
                "market_value_base": sum(row["market_value_base"] or 0 for row in rows),
                "weight_pct": sum(row["weight_pct"] or 0 for row in rows),
                "holdings": rows,
            }
        )
    by_asset_class.sort(key=lambda item: item["weight_pct"] or 0, reverse=True)

    data_dates = {
        "stock": stock_date,
        "bond": bond_date,
        "cd": cd_date,
        "deposit": deposit_date,
        "fund": fund_date,
        "cash": cash_date,
        "repo": repo_date,
    }

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "count": len(serialized),
        "snapshot_dates": {
            key: value.isoformat() if value is not None else None
            for key, value in data_dates.items()
        },
        "holdings": serialized,
        "by_asset_class": by_asset_class,
    }
