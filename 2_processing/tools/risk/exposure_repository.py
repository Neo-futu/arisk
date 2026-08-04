"""Data access helpers for exposure calculations (ORM snapshot reads)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure_models import BalancePortfolioAsset, BalancePortfolioMmf, BalancePortfolioNav


@dataclass
class MmfSnapshot:
    wam_days: float
    wal_days: float


async def get_nav_value(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
) -> float | None:
    stmt = select(BalancePortfolioNav.net_asset).where(
        BalancePortfolioNav.port_id == fund_id,
        BalancePortfolioNav.evaluate_date == as_of_date,
        BalancePortfolioNav.class_id.is_(None),
    )
    nav_value = (await db.execute(stmt)).scalar_one_or_none()
    return float(nav_value) if nav_value else None


async def get_mmf_snapshot(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
) -> MmfSnapshot | None:
    stmt = select(BalancePortfolioMmf).where(
        BalancePortfolioMmf.port_id == fund_id,
        BalancePortfolioMmf.evaluate_date == as_of_date,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return None
    return MmfSnapshot(
        wam_days=float(row.wam_days or 0),
        wal_days=float(row.wal_days or 0),
    )


async def get_asset_allocation(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
) -> dict[str, float]:
    stmt = select(BalancePortfolioAsset.asset_class, BalancePortfolioAsset.market_value).where(
        BalancePortfolioAsset.port_id == fund_id,
        BalancePortfolioAsset.evaluate_date == as_of_date,
    )
    rows = (await db.execute(stmt)).all()
    return {str(row.asset_class): float(row.market_value or 0) for row in rows}
