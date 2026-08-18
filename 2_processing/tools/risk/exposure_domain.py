"""Shared exposure domain types, constants and compliance rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
    effective_limits: dict[str, float] = field(default_factory=dict)
    compliance_details: list[dict[str, Any]] = field(default_factory=list)
    rule_trace: dict[str, dict[str, Any]] = field(default_factory=dict)
    is_compliant: bool = True


def evaluate_mmf_compliance(
    result: ExposureResult,
    nav: float,
    limits: dict[str, float] | None = None,
) -> tuple[dict[str, bool], list[dict[str, Any]], dict[str, float]]:
    effective = {
        "MMF_WAM": float(MMF_WAM_LIMIT_DAYS),
        "MMF_WAL": float(MMF_WAL_LIMIT_DAYS),
        "MMF_DAILY_LIQUID": float(MMF_DAILY_LIQUID_MIN_PCT),
        "MMF_WEEKLY_LIQUID": float(MMF_WEEKLY_LIQUID_MIN_PCT),
        "MMF_SINGLE_ISSUER": float(MMF_SINGLE_ENTITY_MAX_PCT),
        "MMF_ISSUER_GROUP": float(MMF_GROUP_MAX_PCT),
    }
    if limits:
        effective.update(limits)

    max_issuer_pct = max((v / nav * 100 for v in result.by_issuer.values()), default=0.0) if nav > 0 else 0.0
    max_group_pct = max((v / nav * 100 for v in result.by_group.values()), default=0.0) if nav > 0 else 0.0

    checks = [
        {
            "rule_code": "MMF_WAM",
            "breach_code": "WAM_BREACH",
            "rule_name": "Weighted Average Maturity",
            "current_value": float(result.wam_days),
            "limit_value": float(effective["MMF_WAM"]),
            "operator": "<=",
            "unit": "DAYS",
            "is_breached": float(result.wam_days) > float(effective["MMF_WAM"]),
        },
        {
            "rule_code": "MMF_WAL",
            "breach_code": "WAL_BREACH",
            "rule_name": "Weighted Average Life",
            "current_value": float(result.wal_days),
            "limit_value": float(effective["MMF_WAL"]),
            "operator": "<=",
            "unit": "DAYS",
            "is_breached": float(result.wal_days) > float(effective["MMF_WAL"]),
        },
        {
            "rule_code": "MMF_DAILY_LIQUID",
            "breach_code": "DAILY_LIQUID_BREACH",
            "rule_name": "Daily Liquid Assets",
            "current_value": float(result.daily_liquid_pct),
            "limit_value": float(effective["MMF_DAILY_LIQUID"]),
            "operator": ">=",
            "unit": "PCT",
            "is_breached": float(result.daily_liquid_pct) < float(effective["MMF_DAILY_LIQUID"]),
        },
        {
            "rule_code": "MMF_WEEKLY_LIQUID",
            "breach_code": "WEEKLY_LIQUID_BREACH",
            "rule_name": "Weekly Liquid Assets",
            "current_value": float(result.weekly_liquid_pct),
            "limit_value": float(effective["MMF_WEEKLY_LIQUID"]),
            "operator": ">=",
            "unit": "PCT",
            "is_breached": float(result.weekly_liquid_pct) < float(effective["MMF_WEEKLY_LIQUID"]),
        },
        {
            "rule_code": "MMF_SINGLE_ISSUER",
            "breach_code": "SINGLE_ENTITY_BREACH",
            "rule_name": "Single Issuer Concentration",
            "current_value": float(max_issuer_pct),
            "limit_value": float(effective["MMF_SINGLE_ISSUER"]),
            "operator": "<=",
            "unit": "PCT",
            "is_breached": float(max_issuer_pct) > float(effective["MMF_SINGLE_ISSUER"]),
        },
        {
            "rule_code": "MMF_ISSUER_GROUP",
            "breach_code": "GROUP_BREACH",
            "rule_name": "Issuer Group Concentration",
            "current_value": float(max_group_pct),
            "limit_value": float(effective["MMF_ISSUER_GROUP"]),
            "operator": "<=",
            "unit": "PCT",
            "is_breached": float(max_group_pct) > float(effective["MMF_ISSUER_GROUP"]),
        },
    ]

    flags = {check["breach_code"]: True for check in checks if bool(check["is_breached"])}
    return flags, checks, effective


def check_mmf_compliance(
    result: ExposureResult,
    nav: float,
    limits: dict[str, float] | None = None,
) -> dict[str, bool]:
    flags, _, _ = evaluate_mmf_compliance(result=result, nav=nav, limits=limits)
    return flags
