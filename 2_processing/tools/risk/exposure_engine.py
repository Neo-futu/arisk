"""暴露分析引擎 — 對齊 fsi schema 實際表結構。

數據來源：
  balance_portfolio_nav   → NAV（net_asset）
  balance_portfolio_mmf   → WAM / WAL（預計算，直接讀取）
  balance_portfolio_asset → 資產類別佔比
  balance_bond            → 債券持倉（DLA/WLA 計算）
  balance_cd              → 存款證持倉
  balance_deposit         → 定期存款持倉
  balance_repo            → 回購持倉
  balance_cash            → 現金持倉
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# SFC 《單位信託及互惠基金守則》第 8.2 章閾值
MMF_WAM_LIMIT_DAYS       = 60
MMF_WAL_LIMIT_DAYS       = 120
MMF_DAILY_LIQUID_MIN_PCT = 7.5
MMF_WEEKLY_LIQUID_MIN_PCT = 15.0
MMF_SINGLE_ENTITY_MAX_PCT = 10.0
MMF_GROUP_MAX_PCT        = 20.0
MMF_ABS_MAX_PCT          = 15.0


@dataclass
class ExposureResult:
    fund_id: str
    as_of_date: date
    total_nav_hkd: float = 0.0
    wam_days: float = 0.0
    wal_days: float = 0.0
    daily_liquid_pct: float = 0.0
    weekly_liquid_pct: float = 0.0
    by_asset_type: dict[str, float] = field(default_factory=dict)
    by_issuer: dict[str, float] = field(default_factory=dict)
    by_group: dict[str, float] = field(default_factory=dict)
    by_currency: dict[str, float] = field(default_factory=dict)
    by_country: dict[str, float] = field(default_factory=dict)
    by_maturity_bucket: dict[str, float] = field(default_factory=dict)
    breach_flags: dict[str, bool] = field(default_factory=dict)
    is_compliant: bool = True


async def compute_exposure(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
) -> ExposureResult:
    """從 fsi schema 實際持倉表計算暴露指標。"""
    result = ExposureResult(fund_id=fund_id, as_of_date=as_of_date)
    p = {"fid": fund_id, "dt": as_of_date}

    # ── 1. NAV ────────────────────────────────────────────────────────
    nav_row = (await db.execute(
        text("""
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fid AND evaluate_date = :dt AND class_id IS NULL
        """), p,
    )).fetchone()

    if not nav_row or not nav_row.net_asset:
        logger.warning("No NAV found for %s on %s", fund_id, as_of_date)
        return result

    result.total_nav_hkd = float(nav_row.net_asset)
    nav = result.total_nav_hkd

    # ── 2. WAM / WAL（balance_portfolio_mmf 預計算值） ────────────────
    mmf_row = (await db.execute(
        text("""
            SELECT wam_days, wal_days
            FROM fsi.balance_portfolio_mmf
            WHERE port_id = :fid AND evaluate_date = :dt
        """), p,
    )).fetchone()

    if mmf_row:
        result.wam_days = float(mmf_row.wam_days or 0)
        result.wal_days = float(mmf_row.wal_days or 0)

    # ── 3. 資產配置（balance_portfolio_asset） ────────────────────────
    asset_rows = (await db.execute(
        text("""
            SELECT asset_class::text, market_value
            FROM fsi.balance_portfolio_asset
            WHERE port_id = :fid AND evaluate_date = :dt
        """), p,
    )).fetchall()

    for row in asset_rows:
        mv = float(row.market_value or 0)
        result.by_asset_type[row.asset_class] = mv

    # ── 4. 現金 ───────────────────────────────────────────────────────
    cash_row = (await db.execute(
        text("""
            SELECT COALESCE(SUM(amount_base_ccy), SUM(amount), 0) AS cash
            FROM fsi.balance_cash
            WHERE port_id = :fid AND evaluate_date = :dt
        """), p,
    )).fetchone()
    cash = float(cash_row.cash or 0) if cash_row else 0.0

    # ── 5. 流動性計算（DLA/WLA，對齊 44_sfc_compliance.sql） ──────────
    # DLA = 現金 + T+1 到期政府債 + T+1 CD + 隔夜存款 + T+1 逆回購
    dla_govbond = float((await db.execute(text("""
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype = 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '1 day'
    """), p)).scalar() or 0)

    dla_cd = float((await db.execute(text("""
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_cd
        WHERE port_id = :fid AND evaluate_date = :dt AND maturity_date <= :dt + INTERVAL '1 day'
    """), p)).scalar() or 0)

    dla_deposit = float((await db.execute(text("""
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_deposit
        WHERE port_id = :fid AND evaluate_date = :dt
          AND (is_overnight = TRUE OR maturity_date <= :dt + INTERVAL '1 day')
    """), p)).scalar() or 0)

    dla_revrepo = float((await db.execute(text("""
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_repo
        WHERE port_id = :fid AND evaluate_date = :dt
          AND repo_type = 'REV_REPO'
          AND COALESCE(actual_maturity_date, maturity_date) <= :dt + INTERVAL '1 day'
    """), p)).scalar() or 0)

    # WLA = 現金 + T+5 到期政府債 + T+5 CD + T+5 存款 + T+5 逆回購 + T+5 信用債
    wla_govbond = float((await db.execute(text("""
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype = 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '5 days'
    """), p)).scalar() or 0)

    wla_cd = float((await db.execute(text("""
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_cd
        WHERE port_id = :fid AND evaluate_date = :dt AND maturity_date <= :dt + INTERVAL '5 days'
    """), p)).scalar() or 0)

    wla_deposit = float((await db.execute(text("""
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_deposit
        WHERE port_id = :fid AND evaluate_date = :dt
          AND (is_overnight = TRUE OR maturity_date <= :dt + INTERVAL '5 days')
    """), p)).scalar() or 0)

    wla_revrepo = float((await db.execute(text("""
        SELECT COALESCE(SUM(principal), 0) AS v
        FROM fsi.balance_repo
        WHERE port_id = :fid AND evaluate_date = :dt
          AND repo_type = 'REV_REPO'
          AND COALESCE(actual_maturity_date, maturity_date) <= :dt + INTERVAL '5 days'
    """), p)).scalar() or 0)

    wla_corpbond = float((await db.execute(text("""
        SELECT COALESCE(SUM(market_value), 0) AS v
        FROM fsi.balance_bond
        WHERE port_id = :fid AND evaluate_date = :dt
          AND asset_subtype != 'BOND_GOVT' AND maturity_date <= :dt + INTERVAL '5 days'
    """), p)).scalar() or 0)

    dla = cash + dla_govbond + dla_cd + dla_deposit + dla_revrepo
    wla = cash + wla_govbond + wla_cd + wla_deposit + wla_revrepo + wla_corpbond

    result.daily_liquid_pct  = dla / nav * 100 if nav > 0 else 0.0
    result.weekly_liquid_pct = wla / nav * 100 if nav > 0 else 0.0

    # ── 6. 發行人集中度（Bond + CD + Deposit 合并） ────────────────────
    issuer_rows = (await db.execute(text("""
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
    """), p)).fetchall()

    for row in issuer_rows:
        mv = float(row.total_mv or 0)
        result.by_issuer[row.issuer_name] = mv
        result.by_group[row.issuer_group] = result.by_group.get(row.issuer_group, 0) + mv

    # ── 7. 合規檢查 ────────────────────────────────────────────────────
    result.breach_flags = _check_mmf_compliance(result, nav)
    result.is_compliant = not any(result.breach_flags.values())
    return result


def _check_mmf_compliance(result: ExposureResult, nav: float) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    flags["WAM_BREACH"]           = result.wam_days > MMF_WAM_LIMIT_DAYS
    flags["WAL_BREACH"]           = result.wal_days > MMF_WAL_LIMIT_DAYS
    flags["DAILY_LIQUID_BREACH"]  = result.daily_liquid_pct < MMF_DAILY_LIQUID_MIN_PCT
    flags["WEEKLY_LIQUID_BREACH"] = result.weekly_liquid_pct < MMF_WEEKLY_LIQUID_MIN_PCT

    if nav > 0 and result.by_issuer:
        max_issuer = max(v / nav * 100 for v in result.by_issuer.values())
        max_group  = max(v / nav * 100 for v in result.by_group.values())
        if max_issuer > MMF_SINGLE_ENTITY_MAX_PCT:
            flags["SINGLE_ENTITY_BREACH"] = True
        if max_group > MMF_GROUP_MAX_PCT:
            flags["GROUP_BREACH"] = True

    return {k: v for k, v in flags.items() if v}
