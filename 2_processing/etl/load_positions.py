"""持倉 ETL：從 Wind 或 CSV 載入持倉快照到 Postgres。"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .fx_converter import convert_to_hkd

logger = logging.getLogger(__name__)


@dataclass
class RawPosition:
    fund_id: str
    as_of_date: date
    asset_id: str
    asset_name: str
    asset_type: str
    issuer_id: str | None
    issuer_name: str | None
    issuer_group: str | None
    currency: str
    face_value: float
    market_value: float
    maturity_date: date | None
    coupon_rate: float | None
    credit_rating: str | None
    rating_agency: str | None
    country: str | None
    sector: str | None


async def load_positions_from_csv(
    csv_path: Path,
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> int:
    """從 CSV 檔案載入持倉，返回載入行數。"""
    rows: list[RawPosition] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            rows.append(
                RawPosition(
                    fund_id=fund_id,
                    as_of_date=as_of_date,
                    asset_id=rec["asset_id"],
                    asset_name=rec.get("asset_name", ""),
                    asset_type=rec.get("asset_type", "UNKNOWN"),
                    issuer_id=rec.get("issuer_id"),
                    issuer_name=rec.get("issuer_name"),
                    issuer_group=rec.get("issuer_group"),
                    currency=rec.get("currency", "HKD"),
                    face_value=float(rec.get("face_value", 0)),
                    market_value=float(rec.get("market_value", 0)),
                    maturity_date=_parse_date(rec.get("maturity_date")),
                    coupon_rate=_safe_float(rec.get("coupon_rate")),
                    credit_rating=rec.get("credit_rating"),
                    rating_agency=rec.get("rating_agency"),
                    country=rec.get("country"),
                    sector=rec.get("sector"),
                )
            )

    return await _upsert_positions(rows, db)


async def _upsert_positions(rows: list[RawPosition], db: AsyncSession) -> int:
    """批量 upsert 持倉到 DB，先刪同日數據再插入。"""
    if not rows:
        return 0

    fund_id = rows[0].fund_id
    as_of_date = rows[0].as_of_date

    await db.execute(
        text("DELETE FROM fsi.positions WHERE fund_id = :fid AND as_of_date = :dt"),
        {"fid": fund_id, "dt": as_of_date},
    )

    total_nav = sum(r.market_value for r in rows)

    for row in rows:
        mv_hkd = await convert_to_hkd(
            row.market_value, row.currency, as_of_date, db  # type: ignore[arg-type]
        )
        weight = (row.market_value / total_nav * 100) if total_nav > 0 else 0.0

        await db.execute(
            text("""
                INSERT INTO fsi.positions (
                    fund_id, as_of_date, asset_id, asset_name, asset_type,
                    issuer_id, issuer_name, issuer_group, currency,
                    face_value, market_value, market_value_hkd, weight_pct,
                    maturity_date, coupon_rate, credit_rating, rating_agency,
                    country, sector
                ) VALUES (
                    :fund_id, :as_of_date, :asset_id, :asset_name, :asset_type,
                    :issuer_id, :issuer_name, :issuer_group, :currency,
                    :face_value, :market_value, :mv_hkd, :weight,
                    :maturity_date, :coupon_rate, :credit_rating, :rating_agency,
                    :country, :sector
                )
            """),
            {
                "fund_id": row.fund_id,
                "as_of_date": row.as_of_date,
                "asset_id": row.asset_id,
                "asset_name": row.asset_name,
                "asset_type": row.asset_type,
                "issuer_id": row.issuer_id,
                "issuer_name": row.issuer_name,
                "issuer_group": row.issuer_group,
                "currency": row.currency,
                "face_value": row.face_value,
                "market_value": row.market_value,
                "mv_hkd": float(mv_hkd),
                "weight": weight,
                "maturity_date": row.maturity_date,
                "coupon_rate": row.coupon_rate,
                "credit_rating": row.credit_rating,
                "rating_agency": row.rating_agency,
                "country": row.country,
                "sector": row.sector,
            },
        )

    await db.commit()
    logger.info("Loaded %d positions for %s on %s", len(rows), fund_id, as_of_date)
    return len(rows)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    from datetime import datetime
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_float(s: str | None) -> float | None:
    try:
        return float(s) if s else None
    except (ValueError, TypeError):
        return None
