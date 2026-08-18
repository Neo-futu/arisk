"""SQL-first exposure engine.

Keeps all exposure reads and aggregations as raw SQL text.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure_domain import ExposureResult, evaluate_mmf_compliance
from .rule_limits import load_effective_mmf_limits_with_trace

logger = logging.getLogger(__name__)


async def compute_exposure_sql(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> ExposureResult:
    result = ExposureResult(fund_id=fund_id, as_of_date=as_of_date)
    p = {"fid": fund_id, "dt": as_of_date}

    nav_row = (
        await db.execute(
            text(
                """
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fid AND evaluate_date = :dt AND class_id IS NULL
            """
            ),
            p,
        )
    ).fetchone()

    if not nav_row or not nav_row.net_asset:
        logger.warning("No NAV found for %s on %s", fund_id, as_of_date)
        return result

    result.total_nav_hkd = float(nav_row.net_asset)
    nav = result.total_nav_hkd

    mmf_row = (
        await db.execute(
            text(
                """
            SELECT wam_days, wal_days
            FROM fsi.balance_portfolio_mmf
            WHERE port_id = :fid AND evaluate_date = :dt
            """
            ),
            p,
        )
    ).fetchone()

    if mmf_row:
        result.wam_days = float(mmf_row.wam_days or 0)
        result.wal_days = float(mmf_row.wal_days or 0)

    asset_rows = (
        await db.execute(
            text(
                """
            SELECT asset_class::text, market_value
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fid AND evaluate_date = :dt
            """
            ),
            p,
        )
    ).fetchall()

    for row in asset_rows:
        result.by_asset_type[str(row.asset_class)] = float(row.market_value or 0)

    cash_row = (
        await db.execute(
            text(
                """
            SELECT COALESCE(SUM(amount_base_ccy), SUM(amount), 0) AS cash
            FROM fsi.balance_cash
            WHERE port_id = :fid AND evaluate_date = :dt
            """
            ),
            p,
        )
    ).fetchone()
    cash = float(cash_row.cash or 0) if cash_row else 0.0

    dla_govbond = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype = 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '1 day'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    dla_cd = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_cd
        WHERE port_id = :fid AND evaluate_date = :dt AND maturity_date <= :dt + INTERVAL '1 day'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    dla_deposit = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_deposit
        WHERE port_id = :fid AND evaluate_date = :dt
          AND (is_overnight = TRUE OR maturity_date <= :dt + INTERVAL '1 day')
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    dla_revrepo = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_repo
        WHERE port_id = :fid AND evaluate_date = :dt
          AND repo_type = 'REV_REPO'
          AND COALESCE(actual_maturity_date, maturity_date) <= :dt + INTERVAL '1 day'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    wla_govbond = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype = 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '5 days'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    wla_cd = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_cd
        WHERE port_id = :fid AND evaluate_date = :dt AND maturity_date <= :dt + INTERVAL '5 days'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    wla_deposit = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_deposit
        WHERE port_id = :fid AND evaluate_date = :dt
          AND (is_overnight = TRUE OR maturity_date <= :dt + INTERVAL '5 days')
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    wla_revrepo = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_repo
        WHERE port_id = :fid AND evaluate_date = :dt
          AND repo_type = 'REV_REPO'
          AND COALESCE(actual_maturity_date, maturity_date) <= :dt + INTERVAL '5 days'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    wla_corpbond = float(
        (
            await db.execute(
                text(
                    """
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype != 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '5 days'
        """
                ),
                p,
            )
        ).scalar()
        or 0
    )

    dla = cash + dla_govbond + dla_cd + dla_deposit + dla_revrepo
    wla = cash + wla_govbond + wla_cd + wla_deposit + wla_revrepo + wla_corpbond

    result.daily_liquid_pct = dla / nav * 100 if nav > 0 else 0.0
    result.weekly_liquid_pct = wla / nav * 100 if nav > 0 else 0.0

    issuer_rows = (
        await db.execute(
            text(
                """
        SELECT issuer_name, issuer_group, COALESCE(SUM(mv), 0) AS total_mv
        FROM (
            SELECT COALESCE(issuer_name, issuer_id, 'UNKNOWN') AS issuer_name,
                   COALESCE(issuer_group, issuer_name, 'UNKNOWN') AS issuer_group,
                   market_value AS mv
            FROM fsi.balance_bond
            WHERE port_id = :fid AND evaluate_date = :dt AND quantity > 0

            UNION ALL
            SELECT COALESCE(issuer_name, issuer_id, 'UNKNOWN'),
                   COALESCE(issuer_group, issuer_name, 'UNKNOWN'),
                   COALESCE(market_value, 0)
            FROM fsi.balance_cd
            WHERE port_id = :fid AND evaluate_date = :dt

            UNION ALL
            SELECT COALESCE(bank_name, bank_id, 'UNKNOWN'),
                   COALESCE(bank_group, bank_name, 'UNKNOWN'),
                   COALESCE(total_value, principal, 0)
            FROM fsi.balance_deposit
            WHERE port_id = :fid AND evaluate_date = :dt
        ) t
        GROUP BY issuer_name, issuer_group
        ORDER BY total_mv DESC
        LIMIT 20
        """
            ),
            p,
        )
    ).fetchall()

    for row in issuer_rows:
        mv = float(row.total_mv or 0)
        result.by_issuer[str(row.issuer_name)] = mv
        group = str(row.issuer_group)
        result.by_group[group] = result.by_group.get(group, 0) + mv

    limits, trace = await load_effective_mmf_limits_with_trace(db, fund_id, as_of_date)
    flags, details, effective = evaluate_mmf_compliance(result, nav, limits)
    result.effective_limits = effective
    result.compliance_details = details
    result.rule_trace = trace
    result.breach_flags = flags
    result.is_compliant = not any(result.breach_flags.values())
    return result


async def find_latest_exposure_date_sql(
    fund_id: str,
    db: AsyncSession,
    as_of_date: date,
) -> date | None:
    row = (
        await db.execute(
            text(
                """
            SELECT evaluate_date
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fid
              AND class_id IS NULL
              AND net_asset > 0
              AND evaluate_date <= :dt
            ORDER BY evaluate_date DESC
            LIMIT 1
            """
            ),
            {"fid": fund_id, "dt": as_of_date},
        )
    ).fetchone()
    return row.evaluate_date if row else None
