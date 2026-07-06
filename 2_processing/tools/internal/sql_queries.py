"""SQL registry for internal MCP read-only queries.

This module belongs to 2_processing so SQL stays centralized in the processing layer.
"""
from __future__ import annotations

from typing import Any

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

GET_POSITIONS_BASE_SQL = (
    "SELECT evaluate_date AS as_of_date, port_id AS fund_id, subject_code, subject_name, currency, "
    "quantity, unit_price, cost, market_value, weight_pct "
    "FROM fsi.balance_valuation_sheet WHERE port_id=$1 AND evaluate_date=$2"
)

GET_RISK_SNAPSHOT_SQL = "SELECT * FROM fsi.svc_risk_snapshot WHERE port_id=$1 AND as_of_date=$2"

GET_NAV_HISTORY_SQL = (
    "SELECT evaluate_date AS nav_date, unit_nav AS nav_per_unit, net_asset AS total_nav, currency "
    "FROM fsi.balance_portfolio_nav "
    "WHERE port_id=$1 AND evaluate_date BETWEEN $2 AND $3 AND currency=$4 "
    "ORDER BY evaluate_date"
)

GET_FUND_LIST_SQL = (
    "SELECT port_id AS fund_id, port_name AS fund_name, port_type AS fund_type, base_currency "
    "FROM fsi.para_portfolio WHERE is_active"
)

GET_VAR_NAV_SERIES_SQL = (
    "SELECT evaluate_date, net_asset FROM fsi.balance_portfolio_nav "
    "WHERE port_id=$1 AND evaluate_date BETWEEN $2 AND $3 AND currency=$4 "
    "AND net_asset IS NOT NULL ORDER BY evaluate_date"
)


def build_get_positions_query(
    fund_id: str,
    as_of_date: str,
    asset_type: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[str, list[Any]]:
    """Build positions SQL with sanitized LIMIT and optional subject name filter."""
    safe_limit = _normalize_limit(limit)
    sql = GET_POSITIONS_BASE_SQL
    params: list[Any] = [fund_id, as_of_date]

    if asset_type:
        sql += " AND subject_name ILIKE $3"
        params.append(f"%{asset_type}%")

    sql += f" ORDER BY weight_pct DESC NULLS LAST LIMIT {safe_limit}"
    return sql, params


def _normalize_limit(value: int | None) -> int:
    if value is None:
        return DEFAULT_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(parsed, MAX_LIMIT))
