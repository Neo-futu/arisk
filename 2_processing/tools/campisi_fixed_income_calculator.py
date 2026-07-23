"""固收 Campisi 歸因計算器。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SQL_FILE_PATH = Path(__file__).parent / "campisi_fixed_income.sql"


def _load_sql_query(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found at: {file_path}")
    return file_path.read_text(encoding="utf-8")


@dataclass
class CampisiRecord:
    fund_id: str
    start_date: date
    end_date: date
    security_code: str
    security_name: str
    weight_pct: float
    total_return_pct: float
    coupon_effect_pct: float
    treasury_effect_pct: float
    spread_effect_pct: float
    selection_effect_pct: float
    contrib_coupon_pct: float
    contrib_treasury_pct: float
    contrib_spread_pct: float
    contrib_selection_pct: float
    contrib_total_pct: float


async def compute_campisi_attribution(
    fund_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> List[CampisiRecord]:
    """執行固收 Campisi 歸因計算。"""
    sql_query = _load_sql_query(SQL_FILE_PATH)

    rows = (
        await db.execute(
            text(sql_query),
            {
                "fid": fund_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    ).fetchall()

    if not rows:
        logger.warning("No data found for Campisi fixed income attribution.")
        return []

    return [
        CampisiRecord(
            fund_id=str(r.fund_id),
            start_date=r.start_date,
            end_date=r.end_date,
            security_code=str(r.security_code),
            security_name=str(r.security_name),
            weight_pct=float(r.weight_pct),
            total_return_pct=float(r.total_return_pct),
            coupon_effect_pct=float(r.coupon_effect_pct),
            treasury_effect_pct=float(r.treasury_effect_pct),
            spread_effect_pct=float(r.spread_effect_pct),
            selection_effect_pct=float(r.selection_effect_pct),
            contrib_coupon_pct=float(r.contrib_coupon_pct),
            contrib_treasury_pct=float(r.contrib_treasury_pct),
            contrib_spread_pct=float(r.contrib_spread_pct),
            contrib_selection_pct=float(r.contrib_selection_pct),
            contrib_total_pct=float(r.contrib_total_pct),
        )
        for r in rows
    ]