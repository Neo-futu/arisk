"""持倉 API Router。"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/{fund_id}")
async def get_positions(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="持倉日期 YYYY-MM-DD")],
    asset_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """取基金持倉列表。"""
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
    params: dict = {"fid": fund_id, "dt": as_of_date}
    if asset_type:
        sql += " AND asset_type = :asset_type"
        params["asset_type"] = asset_type
    sql += " ORDER BY weight_pct DESC NULLS LAST"

    rows = await db.execute(text(sql), params)
    positions = rows.mappings().fetchall()

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "count": len(positions),
        "positions": [dict(p) for p in positions],
    }


@router.get("/{fund_id}/summary")
async def get_position_summary(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    db: AsyncSession = Depends(get_db),
):
    """持倉彙總：總 NAV、資產類型分佈。"""
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
    summary = dict(row.mappings().fetchone() or {})
    return {"fund_id": fund_id, "as_of_date": as_of_date, **summary}
