"""持倉 API Router。"""
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

_VALUATION_SELECT = """
    SELECT
        subject_code AS asset_id,
        subject_name AS asset_name,
        COALESCE(NULLIF(data_source, ''), 'VALUATION') AS asset_type,
        subject_name AS issuer_name,
        NULL::text AS issuer_group,
        currency,
        quantity AS face_value,
        market_value,
        market_value AS market_value_hkd,
        weight_pct,
        NULL::date AS maturity_date,
        NULL::numeric AS coupon_rate,
        NULL::text AS credit_rating,
        NULL::text AS rating_agency,
        NULL::text AS country,
        NULL::text AS sector
    FROM fsi.balance_valuation_sheet
    WHERE port_id = :fid AND evaluate_date = :dt
"""


async def _latest_position_date(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    *,
    use_positions_table: bool,
) -> date | None:
    if use_positions_table:
        latest = (
            await db.execute(
                text(
                    """
                    SELECT MAX(as_of_date)
                    FROM fsi.positions
                    WHERE fund_id = :fid AND as_of_date <= :dt
                    """
                ),
                {"fid": fund_id, "dt": as_of_date},
            )
        ).scalar_one()
        if latest is not None:
            return latest
    return (
        await db.execute(
            text(
                """
                SELECT MAX(evaluate_date)
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fid AND evaluate_date <= :dt
                """
            ),
            {"fid": fund_id, "dt": as_of_date},
        )
    ).scalar_one()


async def _fetch_positions(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    asset_type: str | None,
) -> tuple[list[dict[str, Any]], str]:
    params: dict[str, Any] = {"fid": fund_id, "dt": as_of_date}
    sql = """
        SELECT
            asset_id, asset_name, asset_type,
            issuer_name, issuer_group,
            currency, face_value, market_value, market_value_hkd,
            weight_pct, maturity_date, coupon_rate,
            credit_rating, rating_agency, country, sector
        FROM fsi.positions
        WHERE fund_id = :fid AND as_of_date = :dt
    """
    if asset_type:
        sql += " AND asset_type = :asset_type"
        params["asset_type"] = asset_type
    sql += " ORDER BY weight_pct DESC NULLS LAST"

    try:
        rows = await db.execute(text(sql), params)
        positions = [dict(p) for p in rows.mappings().fetchall()]
        if positions:
            return positions, "fsi.positions"
    except ProgrammingError:
        await db.rollback()

    fallback_sql = _VALUATION_SELECT
    if asset_type:
        fallback_sql += " AND (subject_code ILIKE :asset_type OR COALESCE(data_source, '') ILIKE :asset_type)"
        params["asset_type"] = f"%{asset_type}%"
    fallback_sql += " ORDER BY weight_pct DESC NULLS LAST"
    rows = await db.execute(text(fallback_sql), params)
    return [dict(p) for p in rows.mappings().fetchall()], "fsi.balance_valuation_sheet"


@router.get("/{fund_id}")
async def get_positions(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="持倉日期 YYYY-MM-DD")],
    asset_type: str | None = None,
    fallback: bool = Query(default=True, description="无数据时回退到最近有效日"),
    db: AsyncSession = Depends(get_db),
):
    """取基金持倉列表。"""
    positions, source_table = await _fetch_positions(db, fund_id, as_of_date, asset_type)
    effective = as_of_date
    use_positions_table = source_table == "fsi.positions"

    if fallback and not positions:
        latest = await _latest_position_date(
            db,
            fund_id,
            as_of_date,
            use_positions_table=use_positions_table,
        )
        if latest is not None and latest != as_of_date:
            effective = latest
            positions, source_table = await _fetch_positions(db, fund_id, effective, asset_type)

    return {
        "fund_id": fund_id,
        "as_of_date": effective,
        "requested_date": as_of_date.isoformat(),
        "effective_date": effective.isoformat(),
        "table": source_table,
        "count": len(positions),
        "positions": positions,
    }


@router.get("/{fund_id}/summary")
async def get_position_summary(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    db: AsyncSession = Depends(get_db),
):
    """持倉彙總：總 NAV、資產類型分佈。"""
    try:
        row = await db.execute(
            text("""
                SELECT
                    COUNT(*) AS position_count,
                    SUM(market_value_hkd) AS total_nav_hkd,
                    COUNT(DISTINCT issuer_name) AS issuer_count,
                    COUNT(DISTINCT asset_type) AS asset_type_count
                FROM fsi.positions
                WHERE fund_id = :fid AND as_of_date = :dt
            """),
            {"fid": fund_id, "dt": as_of_date},
        )
    except ProgrammingError:
        await db.rollback()
        row = await db.execute(
            text("""
                SELECT
                    COUNT(*) AS position_count,
                    SUM(market_value) AS total_nav_hkd,
                    COUNT(DISTINCT subject_name) AS issuer_count,
                    COUNT(DISTINCT subject_code) AS asset_type_count
                FROM fsi.balance_valuation_sheet
                WHERE port_id = :fid AND evaluate_date = :dt
            """),
            {"fid": fund_id, "dt": as_of_date},
        )
    summary = dict(row.mappings().fetchone() or {})
    return {"fund_id": fund_id, "as_of_date": as_of_date, **summary}


@router.get("/{fund_id}/nav")
async def get_nav_history(
    fund_id:    str,
    start:      Annotated[date, Query(description="開始日期 YYYY-MM-DD")],
    end:        Annotated[date | None, Query(description="結束日期 YYYY-MM-DD")] = None,
    db:         AsyncSession = Depends(get_db),
):
    """查詢基金 NAV 歷史（來源：fsi.balance_portfolio_nav）。"""
    end_date = end or date.today()
    try:
        rows = await db.execute(
            text("""
                SELECT
                    evaluate_date   AS date,
                    port_id         AS fund_id,
                    currency,
                    net_asset       AS net_asset_hkd,
                    unit_nav,
                    acc_unit_nav,
                    shares_outstanding,
                    day_return
                FROM fsi.balance_portfolio_nav
                WHERE port_id = :fid
                  AND evaluate_date BETWEEN :start AND :end
                ORDER BY evaluate_date ASC
            """),
            {"fid": fund_id, "start": start, "end": end_date},
        )
        records = [dict(r) for r in rows.mappings().fetchall()]
    except ProgrammingError:
        await db.rollback()
        return {"fund_id": fund_id, "start": str(start), "end": str(end_date), "nav_history": [], "error": "NAV 表不存在"}

    return {
        "fund_id":     fund_id,
        "start":       str(start),
        "end":         str(end_date),
        "count":       len(records),
        "nav_history": records,
    }
