"""ORM-first exposure engine.

Uses SQLAlchemy ORM/Core expression APIs (no raw text SQL).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import and_, desc, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure_domain import ExposureResult, check_mmf_compliance
from .exposure_models import (
    BalanceBond,
    BalanceCash,
    BalanceCd,
    BalanceDeposit,
    BalancePortfolioAsset,
    BalancePortfolioMmf,
    BalancePortfolioNav,
    BalanceRepo,
)

logger = logging.getLogger(__name__)


def _to_float(value: object) -> float:
    return float(value or 0)


async def compute_exposure_orm(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> ExposureResult:
    result = ExposureResult(fund_id=fund_id, as_of_date=as_of_date)

    dt1 = as_of_date + timedelta(days=1)
    dt5 = as_of_date + timedelta(days=5)

    nav_stmt = select(BalancePortfolioNav.net_asset).where(
        BalancePortfolioNav.port_id == fund_id,
        BalancePortfolioNav.evaluate_date == as_of_date,
        BalancePortfolioNav.class_id.is_(None),
    )
    nav_value = (await db.execute(nav_stmt)).scalar_one_or_none()

    if not nav_value:
        logger.warning("No NAV found for %s on %s", fund_id, as_of_date)
        return result

    result.total_nav_hkd = float(nav_value)
    nav = result.total_nav_hkd

    mmf_stmt = select(BalancePortfolioMmf).where(
        BalancePortfolioMmf.port_id == fund_id,
        BalancePortfolioMmf.evaluate_date == as_of_date,
    )
    mmf_row = (await db.execute(mmf_stmt)).scalar_one_or_none()
    if mmf_row:
        result.wam_days = _to_float(mmf_row.wam_days)
        result.wal_days = _to_float(mmf_row.wal_days)

    asset_stmt = select(BalancePortfolioAsset.asset_class, BalancePortfolioAsset.market_value).where(
        BalancePortfolioAsset.port_id == fund_id,
        BalancePortfolioAsset.evaluate_date == as_of_date,
    )
    for row in (await db.execute(asset_stmt)).all():
        result.by_asset_type[str(row.asset_class)] = _to_float(row.market_value)

    cash_stmt = select(
        func.coalesce(func.sum(BalanceCash.amount_base_ccy), func.sum(BalanceCash.amount), 0)
    ).where(
        BalanceCash.port_id == fund_id,
        BalanceCash.evaluate_date == as_of_date,
    )
    cash = _to_float((await db.execute(cash_stmt)).scalar())

    dla_govbond_stmt = select(func.coalesce(func.sum(BalanceBond.market_value), 0)).where(
        BalanceBond.port_id == fund_id,
        BalanceBond.evaluate_date == as_of_date,
        BalanceBond.asset_subtype == "BOND_GOVT",
        BalanceBond.maturity_date <= dt1,
    )
    dla_cd_stmt = select(func.coalesce(func.sum(BalanceCd.market_value), 0)).where(
        BalanceCd.port_id == fund_id,
        BalanceCd.evaluate_date == as_of_date,
        BalanceCd.maturity_date <= dt1,
    )
    dla_deposit_stmt = select(func.coalesce(func.sum(BalanceDeposit.principal), 0)).where(
        BalanceDeposit.port_id == fund_id,
        BalanceDeposit.evaluate_date == as_of_date,
        or_(BalanceDeposit.is_overnight.is_(True), BalanceDeposit.maturity_date <= dt1),
    )
    dla_revrepo_stmt = select(func.coalesce(func.sum(BalanceRepo.principal), 0)).where(
        BalanceRepo.port_id == fund_id,
        BalanceRepo.evaluate_date == as_of_date,
        BalanceRepo.repo_type == "REV_REPO",
        func.coalesce(BalanceRepo.actual_maturity_date, BalanceRepo.maturity_date) <= dt1,
    )

    wla_govbond_stmt = select(func.coalesce(func.sum(BalanceBond.market_value), 0)).where(
        BalanceBond.port_id == fund_id,
        BalanceBond.evaluate_date == as_of_date,
        BalanceBond.asset_subtype == "BOND_GOVT",
        BalanceBond.maturity_date <= dt5,
    )
    wla_cd_stmt = select(func.coalesce(func.sum(BalanceCd.market_value), 0)).where(
        BalanceCd.port_id == fund_id,
        BalanceCd.evaluate_date == as_of_date,
        BalanceCd.maturity_date <= dt5,
    )
    wla_deposit_stmt = select(func.coalesce(func.sum(BalanceDeposit.principal), 0)).where(
        BalanceDeposit.port_id == fund_id,
        BalanceDeposit.evaluate_date == as_of_date,
        or_(BalanceDeposit.is_overnight.is_(True), BalanceDeposit.maturity_date <= dt5),
    )
    wla_revrepo_stmt = select(func.coalesce(func.sum(BalanceRepo.principal), 0)).where(
        BalanceRepo.port_id == fund_id,
        BalanceRepo.evaluate_date == as_of_date,
        BalanceRepo.repo_type == "REV_REPO",
        func.coalesce(BalanceRepo.actual_maturity_date, BalanceRepo.maturity_date) <= dt5,
    )
    wla_corpbond_stmt = select(func.coalesce(func.sum(BalanceBond.market_value), 0)).where(
        BalanceBond.port_id == fund_id,
        BalanceBond.evaluate_date == as_of_date,
        BalanceBond.asset_subtype != "BOND_GOVT",
        BalanceBond.maturity_date <= dt5,
    )

    dla = cash + _to_float((await db.execute(dla_govbond_stmt)).scalar()) + _to_float((await db.execute(dla_cd_stmt)).scalar()) + _to_float((await db.execute(dla_deposit_stmt)).scalar()) + _to_float((await db.execute(dla_revrepo_stmt)).scalar())
    wla = cash + _to_float((await db.execute(wla_govbond_stmt)).scalar()) + _to_float((await db.execute(wla_cd_stmt)).scalar()) + _to_float((await db.execute(wla_deposit_stmt)).scalar()) + _to_float((await db.execute(wla_revrepo_stmt)).scalar()) + _to_float((await db.execute(wla_corpbond_stmt)).scalar())

    result.daily_liquid_pct = dla / nav * 100 if nav > 0 else 0.0
    result.weekly_liquid_pct = wla / nav * 100 if nav > 0 else 0.0

    bond_issuer = select(
        func.coalesce(BalanceBond.issuer_name, BalanceBond.issuer_id, literal("UNKNOWN")).label("issuer_name"),
        func.coalesce(BalanceBond.issuer_group, BalanceBond.issuer_name, literal("UNKNOWN")).label("issuer_group"),
        BalanceBond.market_value.label("mv"),
    ).where(
        BalanceBond.port_id == fund_id,
        BalanceBond.evaluate_date == as_of_date,
        BalanceBond.quantity > 0,
    )

    cd_issuer = select(
        func.coalesce(BalanceCd.issuer_name, BalanceCd.issuer_id, literal("UNKNOWN")).label("issuer_name"),
        func.coalesce(BalanceCd.issuer_group, BalanceCd.issuer_name, literal("UNKNOWN")).label("issuer_group"),
        func.coalesce(BalanceCd.market_value, 0).label("mv"),
    ).where(
        BalanceCd.port_id == fund_id,
        BalanceCd.evaluate_date == as_of_date,
    )

    deposit_issuer = select(
        func.coalesce(BalanceDeposit.bank_name, BalanceDeposit.bank_id, literal("UNKNOWN")).label("issuer_name"),
        func.coalesce(BalanceDeposit.bank_group, BalanceDeposit.bank_name, literal("UNKNOWN")).label("issuer_group"),
        func.coalesce(BalanceDeposit.total_value, BalanceDeposit.principal, 0).label("mv"),
    ).where(
        BalanceDeposit.port_id == fund_id,
        BalanceDeposit.evaluate_date == as_of_date,
    )

    combined = union_all(bond_issuer, cd_issuer, deposit_issuer).subquery("issuer_union")
    issuer_stmt = (
        select(
            combined.c.issuer_name,
            combined.c.issuer_group,
            func.coalesce(func.sum(combined.c.mv), 0).label("total_mv"),
        )
        .group_by(combined.c.issuer_name, combined.c.issuer_group)
        .order_by(desc("total_mv"))
        .limit(20)
    )

    for row in (await db.execute(issuer_stmt)).all():
        mv = _to_float(row.total_mv)
        issuer = str(row.issuer_name)
        group = str(row.issuer_group)
        result.by_issuer[issuer] = mv
        result.by_group[group] = result.by_group.get(group, 0) + mv

    result.breach_flags = check_mmf_compliance(result, nav)
    result.is_compliant = not any(result.breach_flags.values())
    return result


async def find_latest_exposure_date_orm(
    fund_id: str,
    db: AsyncSession,
    as_of_date: date,
) -> date | None:
    stmt = (
        select(BalancePortfolioNav.evaluate_date)
        .where(
            BalancePortfolioNav.port_id == fund_id,
            BalancePortfolioNav.class_id.is_(None),
            BalancePortfolioNav.net_asset > 0,
            BalancePortfolioNav.evaluate_date <= as_of_date,
        )
        .order_by(BalancePortfolioNav.evaluate_date.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
