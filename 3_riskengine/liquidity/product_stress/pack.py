"""投资风险 · 产品压力测试 Tab 业务模块（Bloomberg LQAP）。

页面对应 ``/investment-risk/indicators`` → 产品压力测试（``liquidity`` 域签）。
业务能力（非 UI）：

1. **变现假设** — 赎回比例、Target Cost 倍数、是否计入当日、情景
2. **组合概览** — 市值 / 价差 / 波动 / Pct of EDV / Horizon / Global Score
3. **赎回情景** — Nominal / Cost / Value / Residual
4. **期限分析** — Horizon 分桶（%MV · #Positions · 汇总表）
5. **个券压力明细** — Stress Details
6. **LQA 字段覆盖** — LQA_* 有值只数与口径说明

模型相对独立：本包不读库、不 import ``2_processing``；持仓经
``meta.lqa_positions``（已 enrich）或 ``meta.holdings`` + ADTV/价差/阶梯注入，
底层计算复用同目录 ``lqa_fields`` / ``lqap``。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .. import lqa_fields as F
from .. import lqap as L

BUSINESS_MODULES = (
    "assumptions",
    "overview",
    "redemption",
    "horizon_analysis",
    "stress_details",
    "field_coverage",
)

HORIZON_NOTE = (
    "流动性口径：股票类=参与率×ADTV；债券/CD=bid-ask（非参与率拆天）；"
    "现金/存款/回购=合约期限。"
)


def _positions_from_meta(meta: Mapping[str, Any], as_of: Any) -> list[dict[str, Any]]:
    if meta.get("lqa_positions"):
        return [dict(row) for row in meta["lqa_positions"]]
    holdings = [dict(row) for row in (meta.get("holdings") or ())]
    if not holdings:
        return []
    ladder_raw = meta.get("fi_horizon_ladder")
    ladder = F.normalize_fi_horizon_ladder(ladder_raw) if ladder_raw is not None else None
    return F.enrich_book(
        holdings,
        adtv_by_code=dict(meta.get("adtv_by_code") or {}),
        bid_ask_bps_by_asset=dict(meta.get("bid_ask_bps_by_asset") or {}),
        as_of_date=meta.get("as_of_date") or as_of,
        fi_horizon_ladder=ladder,
    )


def module_assumptions(
    analytics: Mapping[str, Any],
    *,
    scenario_code: str,
    redemption_pct: float,
    cost_multiple: float,
    include_current_day: bool,
) -> dict[str, Any]:
    scenario = dict(analytics.get("scenario") or {})
    factors = L.scenario(scenario_code)
    return {
        "module": "assumptions",
        "scenario": scenario,
        "scenarios": list(analytics.get("scenarios") or []),
        "redemption_pct": float(redemption_pct),
        "target_cost": "Bid-Ask",
        "cost_multiple": float(cost_multiple),
        "include_current_day": bool(include_current_day),
        "day_factor": factors[2],
        "cost_factor": factors[3],
        "volume_scale": factors[4],
        "note": "改参后需重新压力测试计算；情景拉伸天数/成本/股票类 volume_scale。",
    }


def module_overview(analytics: Mapping[str, Any]) -> dict[str, Any]:
    overview = dict(analytics.get("overview") or {})
    return {"module": "overview", **overview}


def module_redemption(analytics: Mapping[str, Any]) -> dict[str, Any]:
    redemption = dict(analytics.get("redemption") or {})
    return {"module": "redemption", **redemption}


def module_horizon_analysis(analytics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "module": "horizon_analysis",
        "horizons": list(analytics.get("horizons") or []),
        "not_covered_positions": analytics.get("not_covered_positions", 0),
        "buckets": [row[0] for row in L.HORIZONS] + ["not_covered"],
        "note": HORIZON_NOTE,
    }


def module_stress_details(analytics: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(analytics.get("securities") or [])
    return {
        "module": "stress_details",
        "securities": rows,
        "count": len(rows),
        "columns": (
            "security_code",
            "security_name",
            "market_value",
            "mv_weight_pct",
            "liq_horizon_days",
            "scenario_lqdty_class",
            "hk_sfc_port_lqdty_class",
            "unif_mkt_imp_cost",
            "bid_ask_bps",
            "expected_daily_volume",
            "cost",
            "sector_score",
            "liquidity_sector",
        ),
    }


def module_field_coverage(analytics: Mapping[str, Any], position_count: int) -> dict[str, Any]:
    fields = list(analytics.get("lqa_fields") or [])
    return {
        "module": "field_coverage",
        "lqa_fields": fields,
        "lqa_present_count": analytics.get("lqa_present_count", len(L.LQA_FIELDS)),
        "lqa_populated_fields": analytics.get("lqa_populated_fields", 0),
        "lqa_proxy_positions": position_count,
        "horizon_note": HORIZON_NOTE,
        "catalog": [
            {"field": name, "key": key, "source": source} for name, key, source in L.LQA_FIELDS
        ],
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    scenario_code: str = "SEVERE",
    redemption_pct: float = 100.0,
    cost_multiple: float = 0.5,
    include_current_day: bool = True,
) -> dict[str, Any]:
    """产品压力测试 Tab 六大业务模块打包。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    positions = _positions_from_meta(info, snapshot.as_of_date)
    analytics = L.analyze(
        positions,
        scenario_code=scenario_code,
        redemption_pct=redemption_pct,
        cost_multiple=cost_multiple,
        include_current_day=include_current_day,
    )

    assumptions = module_assumptions(
        analytics,
        scenario_code=scenario_code,
        redemption_pct=redemption_pct,
        cost_multiple=cost_multiple,
        include_current_day=include_current_day,
    )
    overview = module_overview(analytics)
    redemption = module_redemption(analytics)
    horizon = module_horizon_analysis(analytics)
    stress = module_stress_details(analytics)
    coverage = module_field_coverage(analytics, len(positions))

    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/indicators",
        "tab": "product-stress",
        "domain_key": "liquidity",
        "fund_id": str(info.get("fund_id") or snapshot.fund_id),
        "as_of_date": (
            info.get("as_of_date").isoformat()
            if hasattr(info.get("as_of_date"), "isoformat")
            else str(info.get("as_of_date") or snapshot.as_of_date.isoformat())
        ),
        "data_as_of": info.get("data_as_of")
        or (
            info.get("as_of_date").isoformat()
            if hasattr(info.get("as_of_date"), "isoformat")
            else snapshot.as_of_date.isoformat()
        ),
        "currency": str(info.get("currency") or getattr(snapshot, "reporting_currency", None) or "USD"),
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "assumptions": assumptions,
            "overview": overview,
            "redemption": redemption,
            "horizon_analysis": horizon,
            "stress_details": stress,
            "field_coverage": coverage,
        },
        # HTTP LqaPortfolioAnalytics 同形
        "scenario": analytics["scenario"],
        "scenarios": analytics["scenarios"],
        "assumptions": analytics["assumptions"],
        "overview": analytics["overview"],
        "redemption": analytics["redemption"],
        "horizons": analytics["horizons"],
        "securities": analytics["securities"],
        "not_covered_positions": analytics["not_covered_positions"],
        "lqa_fields": analytics["lqa_fields"],
        "lqa_present_count": analytics["lqa_present_count"],
        "lqa_populated_fields": analytics["lqa_populated_fields"],
        "lqa_proxy_positions": len(positions),
        "lqa_missing_positions": 0,
        "lqa_input": "meta.lqa_positions | meta.holdings + adtv/bid_ask/ladder",
        "message": None if positions else "无持仓，无法生成 LQAP。",
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    assumptions = modules.get("assumptions") or {}
    for key in ("scenario", "redemption_pct", "cost_multiple", "include_current_day"):
        if key not in assumptions:
            errors.append(f"assumptions.{key}")
    overview = modules.get("overview") or {}
    for key in ("market_value", "positions", "liq_horizon_days", "global_score"):
        if key not in overview:
            errors.append(f"overview.{key}")
    redemption = modules.get("redemption") or {}
    for key in ("nominal", "cost", "value", "residual_market_value"):
        if key not in redemption:
            errors.append(f"redemption.{key}")
    horizon = modules.get("horizon_analysis") or {}
    ids = {row.get("id") for row in (horizon.get("horizons") or [])}
    for hid, _lab, _lo, _hi in L.HORIZONS:
        if hid not in ids:
            errors.append(f"horizon_analysis.{hid}")
    if "not_covered" not in ids:
        errors.append("horizon_analysis.not_covered")
    stress = modules.get("stress_details") or {}
    if "securities" not in stress:
        errors.append("stress_details.securities")
    coverage = modules.get("field_coverage") or {}
    if not coverage.get("lqa_fields"):
        errors.append("field_coverage.lqa_fields")
    if coverage.get("lqa_present_count") != len(L.LQA_FIELDS):
        errors.append("field_coverage.lqa_present_count")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
