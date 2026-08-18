"""Load effective risk limits from regulatory, contract and internal rule tables."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure_domain import (
    MMF_DAILY_LIQUID_MIN_PCT,
    MMF_GROUP_MAX_PCT,
    MMF_SINGLE_ENTITY_MAX_PCT,
    MMF_WAL_LIMIT_DAYS,
    MMF_WAM_LIMIT_DAYS,
    MMF_WEEKLY_LIQUID_MIN_PCT,
)

DEFAULT_MMF_LIMITS: dict[str, float] = {
    "MMF_WAM": float(MMF_WAM_LIMIT_DAYS),
    "MMF_WAL": float(MMF_WAL_LIMIT_DAYS),
    "MMF_DAILY_LIQUID": float(MMF_DAILY_LIQUID_MIN_PCT),
    "MMF_WEEKLY_LIQUID": float(MMF_WEEKLY_LIQUID_MIN_PCT),
    "MMF_SINGLE_ISSUER": float(MMF_SINGLE_ENTITY_MAX_PCT),
    "MMF_ISSUER_GROUP": float(MMF_GROUP_MAX_PCT),
}

_LIMIT_DIRECTIONS = {
    "MMF_WAM": "MAX",
    "MMF_WAL": "MAX",
    "MMF_DAILY_LIQUID": "MIN",
    "MMF_WEEKLY_LIQUID": "MIN",
    "MMF_SINGLE_ISSUER": "MAX",
    "MMF_ISSUER_GROUP": "MAX",
}


async def load_effective_mmf_limits_with_trace(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
) -> tuple[dict[str, float], dict[str, dict[str, object]]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT rule_code, limit_direction, limit_value, source_type
                FROM (
                    SELECT rule_code, limit_direction, limit_value, 'regulatory'::text AS source_type
                                        FROM fsi.para_risk_limit_regulatory r
                                        JOIN fsi.para_risk_rule_application a
                                            ON a.rule_type='regulatory' AND a.rule_id=r.limit_id
                                        WHERE a.apply_scope = 'portfolio'
                                            AND a.port_id = :fid
                                            AND a.is_active = TRUE
                                            AND a.effective_date <= :dt
                                            AND (a.expiry_date IS NULL OR a.expiry_date >= :dt)
                                            AND r.is_active = TRUE
                                            AND r.effective_date <= :dt
                                            AND (r.expiry_date IS NULL OR r.expiry_date >= :dt)

                    UNION ALL

                    SELECT limit_code AS rule_code, 'MIN' AS limit_direction, lower_limit AS limit_value, 'internal'::text AS source_type
                                        FROM fsi.para_risk_limit_internal r
                                        JOIN fsi.para_risk_rule_application a
                                            ON a.rule_type='internal' AND a.rule_id=r.limit_id
                                        WHERE a.apply_scope = 'portfolio'
                                            AND a.port_id = :fid
                                            AND a.is_active = TRUE
                                            AND a.effective_date <= :dt
                                            AND (a.expiry_date IS NULL OR a.expiry_date >= :dt)
                                            AND r.is_active = TRUE
                                            AND r.begin_date <= :dt
                                            AND (r.end_date IS NULL OR r.end_date >= :dt)
                                            AND r.lower_limit IS NOT NULL

                    UNION ALL

                    SELECT limit_code AS rule_code, 'MAX' AS limit_direction, upper_limit AS limit_value, 'internal'::text AS source_type
                                        FROM fsi.para_risk_limit_internal r
                                        JOIN fsi.para_risk_rule_application a
                                            ON a.rule_type='internal' AND a.rule_id=r.limit_id
                                        WHERE a.apply_scope = 'portfolio'
                                            AND a.port_id = :fid
                                            AND a.is_active = TRUE
                                            AND a.effective_date <= :dt
                                            AND (a.expiry_date IS NULL OR a.expiry_date >= :dt)
                                            AND r.is_active = TRUE
                                            AND r.begin_date <= :dt
                                            AND (r.end_date IS NULL OR r.end_date >= :dt)
                                            AND r.upper_limit IS NOT NULL

                    UNION ALL

                    SELECT rule_code, 'MIN' AS limit_direction, lower_limit AS limit_value, 'contract'::text AS source_type
                                        FROM fsi.para_risk_limit_contract r
                                        JOIN fsi.para_risk_rule_application a
                                            ON a.rule_type='contract' AND a.rule_id=r.limit_id
                                        WHERE a.apply_scope = 'portfolio'
                                            AND a.port_id = :fid
                                            AND a.is_active = TRUE
                                            AND a.effective_date <= :dt
                                            AND (a.expiry_date IS NULL OR a.expiry_date >= :dt)
                                            AND r.is_active = TRUE
                                            AND r.begin_date <= :dt
                                            AND (r.end_date IS NULL OR r.end_date >= :dt)
                                            AND r.lower_limit IS NOT NULL

                    UNION ALL

                    SELECT rule_code, 'MAX' AS limit_direction, upper_limit AS limit_value, 'contract'::text AS source_type
                                        FROM fsi.para_risk_limit_contract r
                                        JOIN fsi.para_risk_rule_application a
                                            ON a.rule_type='contract' AND a.rule_id=r.limit_id
                                        WHERE a.apply_scope = 'portfolio'
                                            AND a.port_id = :fid
                                            AND a.is_active = TRUE
                                            AND a.effective_date <= :dt
                                            AND (a.expiry_date IS NULL OR a.expiry_date >= :dt)
                                            AND r.is_active = TRUE
                                            AND r.begin_date <= :dt
                                            AND (r.end_date IS NULL OR r.end_date >= :dt)
                                            AND r.upper_limit IS NOT NULL
                ) t
                """
            ),
            {"fid": fund_id, "dt": as_of_date},
        )
    ).fetchall()

    limits = dict(DEFAULT_MMF_LIMITS)
    configured: set[str] = set()
    trace: dict[str, dict[str, object]] = {
        code: {
            "regulatory": 0,
            "contract": 0,
            "internal": 0,
            "total": 0,
            "used_default": True,
            "direction": _LIMIT_DIRECTIONS[code],
        }
        for code in DEFAULT_MMF_LIMITS
    }

    for row in rows:
        code = str(row.rule_code)
        if code not in _LIMIT_DIRECTIONS or row.limit_value is None:
            continue
        direction = str(row.limit_direction).upper()
        if direction != _LIMIT_DIRECTIONS[code]:
            continue

        source_type = str(getattr(row, "source_type", "regulatory"))
        if source_type in ("regulatory", "contract", "internal"):
            trace[code][source_type] = int(trace[code][source_type]) + 1
        trace[code]["total"] = int(trace[code]["total"]) + 1

        value = float(row.limit_value)
        if code not in configured:
            limits[code] = value
            configured.add(code)
            trace[code]["used_default"] = False
        elif direction == "MAX":
            limits[code] = min(limits[code], value)
            trace[code]["used_default"] = False
        else:
            limits[code] = max(limits[code], value)
            trace[code]["used_default"] = False

    return limits, trace


async def load_effective_mmf_limits(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
) -> dict[str, float]:
    """Return effective MMF thresholds, combining all active rule classes.

    MAX rules use the lowest configured value; MIN rules use the highest value.
    This makes regulatory, contract and internal rules converge to the strictest
    effective threshold. Missing configuration falls back to code defaults.
    """
    limits, _ = await load_effective_mmf_limits_with_trace(db=db, fund_id=fund_id, as_of_date=as_of_date)
    return limits


async def load_effective_pretrade_limits(
    db: AsyncSession,
    fund_id: str,
    as_of_date: date,
    asset_class: str,
    trade_side: str,
) -> tuple[dict[str, float], list[dict[str, object]]]:
    """Load active trade/pretrade bindings and aggregate strictest supported limits."""
    rows = (
        await db.execute(
            text(
                """
                SELECT * FROM (
                    SELECT r.rule_code AS code, r.rule_name AS name, r.dimension,
                           r.limit_direction AS direction, r.limit_value AS value,
                           r.limit_unit AS unit, 'regulatory'::text AS rule_type,
                           a.application_id, a.priority
                    FROM fsi.para_risk_limit_regulatory r
                    JOIN fsi.para_risk_rule_application a
                      ON a.rule_type='regulatory' AND a.rule_id=r.limit_id
                    WHERE r.is_active=TRUE AND r.effective_date<=:dt
                      AND (r.expiry_date IS NULL OR r.expiry_date>=:dt)

                    UNION ALL

                    SELECT r.limit_code, r.limit_name, r.dimension, 'MAX', r.upper_limit,
                           r.limit_unit, 'internal'::text, a.application_id, a.priority
                    FROM fsi.para_risk_limit_internal r
                    JOIN fsi.para_risk_rule_application a
                      ON a.rule_type='internal' AND a.rule_id=r.limit_id
                    WHERE r.is_active=TRUE AND r.begin_date<=:dt
                      AND (r.end_date IS NULL OR r.end_date>=:dt) AND r.upper_limit IS NOT NULL

                    UNION ALL

                    SELECT r.rule_code, r.rule_name, r.dimension, 'MAX', r.upper_limit,
                           r.limit_unit, 'contract'::text, a.application_id, a.priority
                    FROM fsi.para_risk_limit_contract r
                    JOIN fsi.para_risk_rule_application a
                      ON a.rule_type='contract' AND a.rule_id=r.limit_id
                    WHERE r.is_active=TRUE AND r.begin_date<=:dt
                      AND (r.end_date IS NULL OR r.end_date>=:dt) AND r.upper_limit IS NOT NULL
                ) rules
                JOIN fsi.para_risk_rule_application app ON app.application_id=rules.application_id
                WHERE app.apply_scope IN ('trade', 'pretrade')
                  AND app.is_active=TRUE
                  AND app.effective_date<=:dt
                  AND (app.expiry_date IS NULL OR app.expiry_date>=:dt)
                  AND (app.port_id IS NULL OR app.port_id=:fid)
                  AND (app.instrument_type IS NULL OR UPPER(app.instrument_type)=UPPER(:asset_class))
                  AND (app.trade_side IS NULL OR app.trade_side='BOTH' OR app.trade_side=UPPER(:trade_side))
                ORDER BY rules.priority ASC
                """
            ),
            {
                "dt": as_of_date,
                "fid": fund_id,
                "asset_class": asset_class,
                "trade_side": trade_side,
            },
        )
    ).mappings().all()

    limits = {
        "duration_years": 4.0,
        "issuer_pct_nav": 10.0,
        "tracking_error_proxy_pct": 5.0,
    }
    applied: list[dict[str, object]] = []
    for row in rows:
        dimension = str(row["dimension"] or "").upper()
        code = str(row["code"] or "").upper()
        value = float(row["value"])
        key: str | None = None
        if dimension == "DURATION" or code in {"PRETRADE_DURATION", "MAX_DURATION"}:
            key = "duration_years"
        elif dimension == "ISSUER" or code in {"MMF_SINGLE_ISSUER", "PRETRADE_ISSUER"}:
            key = "issuer_pct_nav"
        elif dimension == "TRACKING_ERROR" or code in {"PRETRADE_TRACKING_ERROR", "MAX_TRACKING_ERROR"}:
            key = "tracking_error_proxy_pct"
        if not key or str(row["direction"]).upper() != "MAX":
            continue
        limits[key] = min(limits[key], value)
        applied.append(
            {
                "application_id": int(row["application_id"]),
                "rule_type": str(row["rule_type"]),
                "code": code,
                "name": str(row["name"] or code),
                "dimension": dimension,
                "limit_value": value,
                "limit_unit": str(row["unit"] or ""),
                "target_limit": key,
            }
        )
    return limits, applied
