"""Portfolio basic information: fund master data + investment managers.

Distinguishes the fund's business investment managers (fsi.para_person via
fsi.para_portfolio_manager) — with role / lead flag / tenure — from platform
login accounts. Also normalises port_type into a coarse fund_category so the UI
can annotate which risk modules are typically applicable.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# fsi.portfolio_type enum → coarse category used for module applicability hints.
_CATEGORY_MAP: dict[str, str] = {
    "MMF": "MONEY_MARKET",
    "BOND": "BOND",
    "EQUITY": "EQUITY",
    "ETF": "EQUITY",
    "INDEX": "EQUITY",
    "BALANCED": "MIXED",
    "HEDGE": "MIXED",
    "PRIVATE": "MIXED",
    "PENSION": "MIXED",
    "MANDATE": "MIXED",
    "SMA": "MIXED",
    "OTHER": "OTHER",
}


async def compute_portfolio_basic_info(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> dict[str, Any]:
    """基金基本信息：主數據、資金類型、最近數據日與投資經理任職記錄。"""
    portfolio_result = await db.execute(
        text(
            """
            SELECT port_id, port_name, port_name_en,
                   port_type::text AS port_type, base_currency,
                   inception_date, close_date, is_active,
                   is_mmf, mmf_wam_limit_days, mmf_wal_limit_days,
                   asset_mgr_id, trustee_id, custodian_id
            FROM fsi.para_portfolio
            WHERE port_id = :fund_id
            """
        ),
        {"fund_id": fund_id},
    )
    portfolio_row = portfolio_result.mappings().first()
    portfolio = dict(portfolio_row) if portfolio_row else {
        "port_id": fund_id,
        "port_name": fund_id,
        "port_type": None,
    }

    port_type = str(portfolio.get("port_type") or "").upper()
    if portfolio.get("is_mmf"):
        fund_category = "MONEY_MARKET"
    else:
        fund_category = _CATEGORY_MAP.get(port_type, "OTHER")
    portfolio["fund_category"] = fund_category

    data_date = (
        await db.execute(
            text(
                """
                SELECT MAX(evaluate_date) AS value
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date},
        )
    ).scalar_one_or_none()

    manager_result = await db.execute(
        text(
            """
            SELECT pp.person_id, pp.person_name, pp.person_name_en,
                   pm.role::text AS role, pm.is_lead,
                   pm.begin_date, pm.end_date,
                   pp.email, pp.sfc_licence_no,
                   (pm.end_date IS NULL) AS is_current
            FROM fsi.para_portfolio_manager pm
            JOIN fsi.para_person pp ON pp.person_id = pm.person_id
            WHERE pm.port_id = :fund_id
            ORDER BY (pm.end_date IS NULL) DESC, pm.is_lead DESC, pm.begin_date DESC
            """
        ),
        {"fund_id": fund_id},
    )
    managers = [dict(row) for row in manager_result.mappings().all()]

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "data_date": data_date,
        "portfolio": portfolio,
        "managers": managers,
    }
