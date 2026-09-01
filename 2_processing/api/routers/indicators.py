"""Indicator explorer APIs — DataJungle-style catalog, compare series, CSV export.

Serves the generic long-format macro/market indicator base
(``fsi.mktdata_indicator_def`` + ``fsi.mktdata_indicator_series``): pick
indicators / country / period / source, get compare time-series and CSV export,
plus editable maintenance of definitions and observations (audited).
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key
from .data_management import _audit, _row_dict

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Bloomberg-style bounded fan-out: comparing more than this is noise, not signal.
MAX_COMPARE = 8

PeriodCode = Literal["1Y", "3Y", "5Y", "10Y", "MAX"]
_PERIOD_YEARS = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10}


class IndicatorDefCreate(BaseModel):
    indicator_id: str = Field(min_length=2, max_length=48, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    indicator_name: str = Field(min_length=1, max_length=160)
    indicator_name_en: str | None = Field(default=None, max_length=160)
    category: str = Field(min_length=1, max_length=48)
    country: str = Field(min_length=2, max_length=2)
    unit: str = Field(min_length=1, max_length=24)
    frequency: Literal["DAILY", "MONTHLY", "QUARTERLY", "ANNUAL"] = "MONTHLY"
    data_source: str = Field(default="MANUAL", min_length=1, max_length=32)
    description: str | None = None

    @field_validator("indicator_id", mode="before")
    @classmethod
    def upper_id(cls, value: Any) -> Any:
        # Run before the pattern constraint so surrounding whitespace is tolerated.
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("country")
    @classmethod
    def upper_country(cls, value: str) -> str:
        return value.strip().upper()


class ObservationUpsert(BaseModel):
    obs_date: date
    value: Decimal
    data_source: str = Field(default="MANUAL", min_length=1, max_length=32)


class ObservationUpdate(BaseModel):
    value: Decimal
    data_source: str | None = Field(default=None, min_length=1, max_length=32)


def _resolve_range(
    period: str | None, start: date | None, end: date | None, latest: date | None
) -> tuple[date, date]:
    """Explicit start/end wins; otherwise a period window anchored on the latest
    observation (so seeded data is always in-frame regardless of the system clock)."""
    anchor = end or latest or date.today()
    if start and end:
        if start > end:
            raise HTTPException(status_code=422, detail="start must not be later than end")
        return start, end
    if start and not end:
        return start, anchor
    years = _PERIOD_YEARS.get((period or "3Y").upper())
    if years is None:  # MAX or unknown → wide-open floor
        return date(1900, 1, 1), anchor
    return date(anchor.year - years, anchor.month, anchor.day), anchor


async def _get_def(db: AsyncSession, indicator_id: str) -> dict[str, Any]:
    row = (
        await db.execute(
            text("SELECT * FROM fsi.mktdata_indicator_def WHERE indicator_id = :id"),
            {"id": indicator_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return _row_dict(row)


@router.get("/catalog", summary="指標目錄與篩選維度")
async def catalog(
    category: str | None = None,
    country: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    where = """
        WHERE is_active = TRUE
          AND (CAST(:category AS text) IS NULL OR category = CAST(:category AS text))
          AND (CAST(:country AS text) IS NULL OR country = CAST(:country AS text))
    """
    params = {
        "category": category.strip() if category else None,
        "country": country.strip().upper() if country else None,
    }
    rows = (
        await db.execute(
            text(
                f"""
                SELECT d.indicator_id, d.indicator_name, d.indicator_name_en,
                       d.category, d.country, d.unit, d.frequency, d.data_source,
                       d.description,
                       (SELECT COUNT(*) FROM fsi.mktdata_indicator_series s
                        WHERE s.indicator_id = d.indicator_id) AS point_count
                FROM fsi.mktdata_indicator_def d {where}
                ORDER BY d.country, d.category, d.indicator_id
                """
            ),
            params,
        )
    ).all()
    dims = (
        await db.execute(
            text(
                """
                SELECT
                  array_agg(DISTINCT country ORDER BY country)   AS countries,
                  array_agg(DISTINCT category ORDER BY category)  AS categories,
                  array_agg(DISTINCT data_source ORDER BY data_source) AS sources
                FROM fsi.mktdata_indicator_def WHERE is_active = TRUE
                """
            )
        )
    ).first()
    return {
        "indicators": [_row_dict(row) for row in rows],
        "countries": list(dims.countries or []),
        "categories": list(dims.categories or []),
        "sources": list(dims.sources or []),
    }


def _parse_ids(indicator_ids: str) -> list[str]:
    ids = [part.strip().upper() for part in indicator_ids.split(",") if part.strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="At least one indicator_id is required")
    if len(ids) > MAX_COMPARE:
        raise HTTPException(status_code=422, detail=f"Compare at most {MAX_COMPARE} indicators")
    # de-dup, preserve order
    return list(dict.fromkeys(ids))


async def _load_series(
    db: AsyncSession,
    ids: list[str],
    period: str | None,
    start: date | None,
    end: date | None,
) -> list[dict[str, Any]]:
    defs = {
        row["indicator_id"]: dict(row)
        for row in (
            await db.execute(
                text(
                    """
                    SELECT indicator_id, indicator_name, indicator_name_en,
                           category, country, unit
                    FROM fsi.mktdata_indicator_def WHERE indicator_id = ANY(:ids)
                    """
                ),
                {"ids": ids},
            )
        ).mappings().all()
    }
    missing = [i for i in ids if i not in defs]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown indicators: {', '.join(missing)}")

    latest = (
        await db.execute(
            text(
                "SELECT MAX(obs_date) FROM fsi.mktdata_indicator_series WHERE indicator_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
    ).scalar()
    range_start, range_end = _resolve_range(period, start, end, latest)

    series: list[dict[str, Any]] = []
    for indicator_id in ids:
        points = (
            await db.execute(
                text(
                    """
                    SELECT obs_date, value FROM fsi.mktdata_indicator_series
                    WHERE indicator_id = :id AND obs_date BETWEEN :start AND :end
                    ORDER BY obs_date
                    """
                ),
                {"id": indicator_id, "start": range_start, "end": range_end},
            )
        ).all()
        meta = defs[indicator_id]
        series.append(
            {
                "indicator_id": indicator_id,
                "name": meta["indicator_name"],
                "name_en": meta["indicator_name_en"],
                "category": meta["category"],
                "country": meta["country"],
                "unit": meta["unit"],
                "points": [{"obs_date": r.obs_date, "value": r.value} for r in points],
            }
        )
    return series


@router.get("/series", summary="指標對比時序")
async def series(
    indicator_ids: str = Query(description="逗號分隔，最多 8 個"),
    period: str | None = Query(default=None, description="1Y/3Y/5Y/10Y/MAX"),
    start: date | None = None,
    end: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ids = _parse_ids(indicator_ids)
    data = await _load_series(db, ids, period, start, end)
    return {"series": data, "count": len(data)}


@router.get("/series/export", summary="指標時序 CSV 導出", response_class=PlainTextResponse)
async def export_series(
    indicator_ids: str = Query(description="逗號分隔，最多 8 個"),
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    ids = _parse_ids(indicator_ids)
    data = await _load_series(db, ids, period, start, end)

    # Wide pivot: one row per date, one column per indicator.
    by_date: dict[date, dict[str, Any]] = {}
    for s in data:
        for point in s["points"]:
            by_date.setdefault(point["obs_date"], {})[s["indicator_id"]] = point["value"]

    buffer = io.StringIO()
    header = ["obs_date", *(s["indicator_id"] for s in data)]
    buffer.write(",".join(header) + "\n")
    for obs_date in sorted(by_date):
        row = [obs_date.isoformat()]
        for s in data:
            value = by_date[obs_date].get(s["indicator_id"])
            row.append("" if value is None else str(value))
        buffer.write(",".join(row) + "\n")

    filename = f"indicators_{'_'.join(ids)[:60]}.csv"
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/defs", status_code=status.HTTP_201_CREATED, summary="新建指標定義")
async def create_def(
    payload: IndicatorDefCreate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    values = payload.model_dump()
    try:
        await db.execute(
            text(
                """
                INSERT INTO fsi.mktdata_indicator_def
                    (indicator_id, indicator_name, indicator_name_en, category,
                     country, unit, frequency, data_source, description)
                VALUES
                    (:indicator_id, :indicator_name, :indicator_name_en, :category,
                     :country, :unit, :frequency, :data_source, :description)
                """
            ),
            values,
        )
        await _audit(
            db,
            event_type="INDICATOR_DEF_CREATED",
            actor=actor,
            port_id=None,
            details={"indicator": values},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Indicator already exists") from exc
    return await _get_def(db, payload.indicator_id)


@router.post("/{indicator_id}/observations", status_code=status.HTTP_201_CREATED, summary="新增/更新觀測點")
async def upsert_observation(
    indicator_id: str,
    payload: ObservationUpsert,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    indicator_id = indicator_id.strip().upper()
    await _get_def(db, indicator_id)
    await db.execute(
        text(
            """
            INSERT INTO fsi.mktdata_indicator_series (indicator_id, obs_date, value, data_source)
            VALUES (:indicator_id, :obs_date, :value, :data_source)
            ON CONFLICT (indicator_id, obs_date)
            DO UPDATE SET value = EXCLUDED.value, data_source = EXCLUDED.data_source, loaded_at = NOW()
            """
        ),
        {"indicator_id": indicator_id, **payload.model_dump()},
    )
    await _audit(
        db,
        event_type="INDICATOR_OBS_UPSERTED",
        actor=actor,
        port_id=None,
        details={"indicator_id": indicator_id, "observation": payload.model_dump()},
    )
    await db.commit()
    return {"indicator_id": indicator_id, "obs_date": payload.obs_date, "value": payload.value}


@router.patch("/{indicator_id}/observations/{obs_date}", summary="修改觀測點")
async def update_observation(
    indicator_id: str,
    obs_date: date,
    payload: ObservationUpdate,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    indicator_id = indicator_id.strip().upper()
    assignments = {"value": payload.value}
    if payload.data_source is not None:
        assignments["data_source"] = payload.data_source
    columns = ", ".join(f"{key} = :{key}" for key in assignments)
    result = await db.execute(
        text(
            f"""
            UPDATE fsi.mktdata_indicator_series SET {columns}, loaded_at = NOW()
            WHERE indicator_id = :indicator_id AND obs_date = :obs_date
            """
        ),
        {"indicator_id": indicator_id, "obs_date": obs_date, **assignments},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Observation not found")
    await _audit(
        db,
        event_type="INDICATOR_OBS_UPDATED",
        actor=actor,
        port_id=None,
        details={"indicator_id": indicator_id, "obs_date": obs_date, "changes": assignments},
    )
    await db.commit()
    return {"indicator_id": indicator_id, "obs_date": obs_date, "value": payload.value}


@router.delete("/{indicator_id}/observations/{obs_date}", summary="刪除觀測點")
async def delete_observation(
    indicator_id: str,
    obs_date: date,
    actor: str = Query(min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    indicator_id = indicator_id.strip().upper()
    result = await db.execute(
        text(
            """
            DELETE FROM fsi.mktdata_indicator_series
            WHERE indicator_id = :indicator_id AND obs_date = :obs_date
            """
        ),
        {"indicator_id": indicator_id, "obs_date": obs_date},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Observation not found")
    await _audit(
        db,
        event_type="INDICATOR_OBS_DELETED",
        actor=actor,
        port_id=None,
        details={"indicator_id": indicator_id, "obs_date": obs_date},
    )
    await db.commit()
    return {"message": "Observation deleted"}
