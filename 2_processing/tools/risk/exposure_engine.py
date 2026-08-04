"""Exposure engine facade.

Provides a stable API while supporting parallel engine implementations:
- sql: raw SQL text
- hybrid: ORM snapshot reads + SQL heavy aggregations
- orm: SQLAlchemy expression/ORM style
"""
from __future__ import annotations

import os
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from .exposure_domain import ExposureResult
from .exposure_engine_hybrid import compute_exposure_hybrid, find_latest_exposure_date_hybrid
from .exposure_engine_orm import compute_exposure_orm, find_latest_exposure_date_orm
from .exposure_engine_sql import compute_exposure_sql, find_latest_exposure_date_sql

ExposureMode = str
SUPPORTED_MODES = {"sql", "hybrid", "orm"}
DEFAULT_MODE = "hybrid"


def _resolve_mode(mode: ExposureMode | None = None) -> ExposureMode:
    resolved = (mode or os.getenv("EXPOSURE_ENGINE_MODE", DEFAULT_MODE) or DEFAULT_MODE).strip().lower()
    return resolved if resolved in SUPPORTED_MODES else DEFAULT_MODE


async def compute_exposure(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    mode: ExposureMode | None = None,
) -> ExposureResult:
    resolved = _resolve_mode(mode)
    if resolved == "sql":
        return await compute_exposure_sql(fund_id=fund_id, as_of_date=as_of_date, db=db)
    if resolved == "orm":
        return await compute_exposure_orm(fund_id=fund_id, as_of_date=as_of_date, db=db)
    return await compute_exposure_hybrid(fund_id=fund_id, as_of_date=as_of_date, db=db)


async def find_latest_exposure_date(
    fund_id: str,
    db: AsyncSession,
    as_of_date: date,
    mode: ExposureMode | None = None,
) -> date | None:
    resolved = _resolve_mode(mode)
    if resolved == "sql":
        return await find_latest_exposure_date_sql(fund_id=fund_id, db=db, as_of_date=as_of_date)
    if resolved == "orm":
        return await find_latest_exposure_date_orm(fund_id=fund_id, db=db, as_of_date=as_of_date)
    return await find_latest_exposure_date_hybrid(fund_id=fund_id, db=db, as_of_date=as_of_date)


__all__ = [
    "ExposureResult",
    "SUPPORTED_MODES",
    "DEFAULT_MODE",
    "compute_exposure",
    "find_latest_exposure_date",
    "compute_exposure_sql",
    "find_latest_exposure_date_sql",
    "compute_exposure_hybrid",
    "find_latest_exposure_date_hybrid",
    "compute_exposure_orm",
    "find_latest_exposure_date_orm",
]
