"""暴露分析引擎：計算組合的各維度暴露及 MMF 合規指標。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# SFC 《單位信託及互惠基金守則》第 8.2 章閾值
MMF_WAM_LIMIT_DAYS = 60
MMF_WAL_LIMIT_DAYS = 120
MMF_MAX_MATURITY_DAYS = 397
MMF_DAILY_LIQUID_MIN_PCT = 7.5
MMF_WEEKLY_LIQUID_MIN_PCT = 15.0
MMF_SINGLE_ENTITY_MAX_PCT = 10.0        # 一般上限
MMF_SINGLE_ENTITY_SFI_PCT = 25.0        # 重要財務機構上限
MMF_GROUP_MAX_PCT = 20.0
MMF_ABS_MAX_PCT = 15.0                  # 資產抵押證券上限
MMF_GOVBOND_SAME_ISSUE_PCT = 30.0


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
    """計算指定日期的持倉暴露指標。"""
    result = ExposureResult(fund_id=fund_id, as_of_date=as_of_date)

    rows = await db.execute(
        text("""
            SELECT
                asset_id, asset_type, issuer_id, issuer_name, issuer_group,
                currency, market_value_hkd, weight_pct,
                maturity_date, asset_type IN ('DEPOSIT','CD') AS is_deposit,
                CASE
                    WHEN maturity_date IS NULL THEN NULL
                    ELSE (maturity_date - :dt)
                END AS days_to_maturity
            FROM fsi.positions
            WHERE fund_id = :fid AND as_of_date = :dt
        """),
        {"fid": fund_id, "dt": as_of_date},
    )
    positions = rows.fetchall()

    if not positions:
        logger.warning("No positions found for %s on %s", fund_id, as_of_date)
        return result

    total_nav = sum(p.market_value_hkd or 0 for p in positions)
    result.total_nav_hkd = total_nav

    # WAM / WAL（以剩餘天數加權）
    wam_numerator = 0.0
    wal_numerator = 0.0
    daily_liquid = 0.0
    weekly_liquid = 0.0

    for p in positions:
        mv = p.market_value_hkd or 0
        w = mv / total_nav if total_nav > 0 else 0
        days = p.days_to_maturity or 0

        wam_numerator += w * min(days, 397)
        wal_numerator += w * days

        if days <= 1:
            daily_liquid += mv
        if days <= 5:
            weekly_liquid += mv

        # 分組彙總
        result.by_asset_type[p.asset_type] = result.by_asset_type.get(p.asset_type, 0) + mv
        issuer_key = p.issuer_name or p.issuer_id or "UNKNOWN"
        result.by_issuer[issuer_key] = result.by_issuer.get(issuer_key, 0) + mv
        group_key = p.issuer_group or issuer_key
        result.by_group[group_key] = result.by_group.get(group_key, 0) + mv
        result.by_currency[p.currency] = result.by_currency.get(p.currency, 0) + mv
        bucket = _maturity_bucket(days)
        result.by_maturity_bucket[bucket] = result.by_maturity_bucket.get(bucket, 0) + mv

    result.wam_days = wam_numerator
    result.wal_days = wal_numerator
    result.daily_liquid_pct = daily_liquid / total_nav * 100 if total_nav > 0 else 0
    result.weekly_liquid_pct = weekly_liquid / total_nav * 100 if total_nav > 0 else 0

    # 合規檢查
    result.breach_flags = _check_mmf_compliance(result, total_nav)
    result.is_compliant = not any(result.breach_flags.values())
    return result


def _maturity_bucket(days: int | float) -> str:
    if days <= 1:
        return "ON/1D"
    elif days <= 7:
        return "2-7D"
    elif days <= 30:
        return "8-30D"
    elif days <= 90:
        return "31-90D"
    elif days <= 180:
        return "91-180D"
    elif days <= 397:
        return "181-397D"
    else:
        return ">397D"


def _check_mmf_compliance(result: ExposureResult, total_nav: float) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    flags["WAM_BREACH"] = result.wam_days > MMF_WAM_LIMIT_DAYS
    flags["WAL_BREACH"] = result.wal_days > MMF_WAL_LIMIT_DAYS
    flags["DAILY_LIQUID_BREACH"] = result.daily_liquid_pct < MMF_DAILY_LIQUID_MIN_PCT
    flags["WEEKLY_LIQUID_BREACH"] = result.weekly_liquid_pct < MMF_WEEKLY_LIQUID_MIN_PCT

    if total_nav > 0:
        max_issuer_pct = max(
            (v / total_nav * 100 for v in result.by_issuer.values()), default=0
        )
        max_group_pct = max(
            (v / total_nav * 100 for v in result.by_group.values()), default=0
        )
        flags["SINGLE_ENTITY_BREACH"] = max_issuer_pct > MMF_SINGLE_ENTITY_MAX_PCT
        flags["GROUP_BREACH"] = max_group_pct > MMF_GROUP_MAX_PCT

    return {k: v for k, v in flags.items() if v}
