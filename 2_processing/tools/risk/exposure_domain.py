"""Shared exposure domain types, constants and compliance rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# SFC 《單位信託及互惠基金守則》第 8.2 章閾值
MMF_WAM_LIMIT_DAYS = 60
MMF_WAL_LIMIT_DAYS = 120
MMF_DAILY_LIQUID_MIN_PCT = 7.5
MMF_WEEKLY_LIQUID_MIN_PCT = 15.0
MMF_SINGLE_ENTITY_MAX_PCT = 10.0
MMF_GROUP_MAX_PCT = 20.0
MMF_ABS_MAX_PCT = 15.0


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


def check_mmf_compliance(result: ExposureResult, nav: float) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    flags["WAM_BREACH"] = result.wam_days > MMF_WAM_LIMIT_DAYS
    flags["WAL_BREACH"] = result.wal_days > MMF_WAL_LIMIT_DAYS
    flags["DAILY_LIQUID_BREACH"] = result.daily_liquid_pct < MMF_DAILY_LIQUID_MIN_PCT
    flags["WEEKLY_LIQUID_BREACH"] = result.weekly_liquid_pct < MMF_WEEKLY_LIQUID_MIN_PCT

    if nav > 0 and result.by_issuer:
        max_issuer = max(v / nav * 100 for v in result.by_issuer.values())
        max_group = max(v / nav * 100 for v in result.by_group.values())
        if max_issuer > MMF_SINGLE_ENTITY_MAX_PCT:
            flags["SINGLE_ENTITY_BREACH"] = True
        if max_group > MMF_GROUP_MAX_PCT:
            flags["GROUP_BREACH"] = True

    return {k: v for k, v in flags.items() if v}
