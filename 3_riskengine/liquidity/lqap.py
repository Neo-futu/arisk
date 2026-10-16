"""LQAP portfolio liquidity analytics.

Pure calculation. Positions carry LQA fields from lqa_fields.enrich_*
(holdings + ADTV + asset-class bid-ask). No database access.

Horizon / cost assumptions follow Bloomberg LQAP split:
- Equity-like: participation × ADTV (volume_scale applies on fallback).
- Fixed income: bid-ask driven (cost always; horizon from enrich, not ADTV).
"""
from __future__ import annotations

from typing import Any

from .lqa_fields import (
    _FIXED_INCOME_ASSETS,
    _VOLUME_HORIZON_ASSETS,
    _fi_horizon_from_bid_ask_bps,
)

# code, label, day stretch, cost stretch, volume participation scale
SCENARIOS: tuple[tuple[str, str, float, float, float], ...] = (
    ("CUSTOM", "Custom", 1.0, 1.0, 1.0),
    ("MILD", "MILD", 1.0, 1.0, 1.0),
    ("MODERATE", "MODERATE", 1.15, 1.2, 0.8),
    ("SEVERE", "SEVERE", 1.4, 1.5, 0.6),
    ("EXTREME", "EXTREME", 1.8, 2.0, 0.4),
    ("RUSSIA98", "RUSSIA98", 1.5, 1.6, 0.55),
    ("OIL08", "OIL08", 1.25, 1.3, 0.75),
    ("BEARSTEARNS08", "BEARSTEARNS08", 1.55, 1.7, 0.5),
    ("LEHMAN08", "LEHMAN08", 1.7, 1.9, 0.45),
    ("GREECE10", "GREECE10", 1.35, 1.4, 0.65),
    ("DEBTCEILING11", "DEBTCEILING11", 1.2, 1.25, 0.8),
    ("EURODEBT11", "EURODEBT11", 1.4, 1.45, 0.6),
    ("BREXIT16", "BREXIT16", 1.2, 1.25, 0.75),
    ("DECEMBER18", "DECEMBER18", 1.3, 1.35, 0.7),
    ("THIRDAVENUE15", "THIRDAVENUE15", 1.6, 1.75, 0.5),
    ("COVID20", "COVID20", 1.65, 1.8, 0.45),
    ("UKRAINE22", "UKRAINE22", 1.35, 1.45, 0.65),
    ("BANKRUN23", "BANKRUN23", 1.9, 2.1, 0.35),
    ("TARIFF25", "TARIFF25", 1.25, 1.3, 0.75),
)

HORIZONS: tuple[tuple[str, str, float, float], ...] = (
    ("le1", "<= 1 day", 0, 1),
    ("d1_3", "1.1 - 3 days", 1.01, 3),
    ("d3_5", "3.1 - 5 days", 3.01, 5),
    ("d5_10", "5.1 - 10 days", 5.01, 10),
    ("d10_15", "10.1 - 15 days", 10.01, 15),
    ("d15_25", "15.1 - 25 days", 15.01, 25),
    ("gt25", "> 25 days", 25.01, 100000),
)

_CLASS_DAYS = {
    "1 day or less": 1.0,
    "2-7 days": 4.0,
    "8-30 days": 19.0,
    "31-90 days": 60.0,
    "91-365 days": 180.0,
    "longer than 365 days": 400.0,
}

# Screen field name, position key, business source.
LQA_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("LQA_PRICE_VOLATILITY", "price_volatility", "久期 × 1% 收益率波动"),
    ("LQA_EXPECTED_DAILY_VOLUME", "expected_daily_volume", "股票类=ADTV；现金/存款/逆回购=市值；债券不驱动天数"),
    ("LQA_BID_ASK_SPREAD", "bid_ask_spread", "债券成本与指示性天数；sfc_liquidity_bucket_def.bid_ask_cost_bps"),
    ("LQA_SECTOR_SCORE", "sector_score", "资产类别流动性得分 − 变现天数"),
    ("LQA_LIQUIDITY_SECTOR", "liquidity_sector", "债券板块，否则资产类别"),
    ("LQA_HK_SFC_PORT_LQDTY_CLASS", "hk_sfc_port_lqdty_class", "由变现天数归类（债券=bid-ask 指示；股票=参与率）"),
    ("LQA_EMPIRICAL_TRADE_COUNT", "empirical_trade_count", "ADTV 样本天数（股票类）"),
    ("LQA_EMPIRICAL_EVALUATION_DATE", "empirical_evaluation_date", "流动性压测估值日"),
    ("LQA_EMPIRICAL_MIN_TRADE_VOLUME", "empirical_min_trade_volume", "样本内仅有 ADTV 时等于日均"),
    ("LQA_EMPIRICAL_SOURCE_DATE", "empirical_source_date", "ADTV 日或估值日"),
    ("LQA_EMPIRICAL_DAYS_SINCE_LST_TRD", "empirical_days_since_last_trade", "估值日当日观察，记 0"),
    ("LQA_EMPIRICAL_AVG_TRADE_VOLUME", "empirical_avg_trade_volume", "预期日成交额（股票类）"),
    ("LQA_EMPIRICAL_MAX_TRADE_VOLUME", "empirical_max_trade_volume", "样本内仅有 ADTV 时等于日均"),
    ("LQA_EMPIRICAL_LOOKBACK_PERIOD", "empirical_lookback_period", "mktdata_adtv.sample_days，默认 30"),
    ("LQA_EMPIRICAL_TOTAL_TRADE_VOLUME", "empirical_total_trade_volume", "日均 × 回看天数"),
)

_PARTICIPATION = 0.10


def scenario(code: str) -> tuple[str, str, float, float, float]:
    key = (code or "SEVERE").upper()
    for item in SCENARIOS:
        if item[0] == key:
            return item
    return SCENARIOS[3]


def _horizon_id(days: float | None) -> str:
    if days is None:
        return "not_covered"
    for hid, _label, lo, hi in HORIZONS:
        if lo <= days <= hi:
            return hid
    return "not_covered"


def _class_for_days(days: float | None) -> str:
    if days is None:
        return "Not Covered"
    if days <= 1:
        return "1 day or less"
    if days <= 7:
        return "2-7 days"
    if days <= 30:
        return "8-30 days"
    if days <= 90:
        return "31-90 days"
    if days <= 365:
        return "91-365 days"
    return "Longer than 365 days"


def _class_days(label: str | None) -> float | None:
    if not label:
        return None
    return _CLASS_DAYS.get(str(label).strip().lower())


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _days_for(position: dict[str, Any], day_factor: float, volume_scale: float, shift: float) -> float | None:
    explicit = _num(position.get("liq_horizon_days"))
    if explicit is not None:
        return max(explicit, 0.0) * day_factor + shift
    mapped = _class_days(position.get("hk_sfc_port_lqdty_class"))
    if mapped is not None:
        return mapped * day_factor + shift
    asset = str(position.get("asset_category") or "")
    # Bonds/CD: never fall back to ADTV × participation.
    if asset in _FIXED_INCOME_ASSETS:
        spread = _num(position.get("bid_ask_spread"))
        bps = _num(position.get("bid_ask_bps"))
        if bps is None and spread is not None:
            bps = spread * 10000.0
        base = _fi_horizon_from_bid_ask_bps(bps)
        if base is None:
            return None
        return base * day_factor + shift
    if asset in _VOLUME_HORIZON_ASSETS or not asset:
        mv = _num(position.get("market_value")) or 0.0
        edv = _num(position.get("expected_daily_volume"))
        capacity = (edv or 0.0) * _PARTICIPATION * volume_scale
        if mv > 0 and capacity > 0:
            return mv / capacity * day_factor + shift
    return None


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def analyze(
    positions: list[dict[str, Any]],
    *,
    scenario_code: str = "SEVERE",
    redemption_pct: float = 100.0,
    cost_multiple: float = 0.5,
    include_current_day: bool = True,
) -> dict[str, Any]:
    """Aggregate a book into the LQAP horizon / cost / overview contract."""
    code, label, day_factor, cost_factor, volume_scale = scenario(scenario_code)
    shift = 0.0 if include_current_day else 1.0
    buckets: dict[str, dict[str, Any]] = {
        hid: {
            "id": hid,
            "label": lab,
            "market_value": 0.0,
            "positions": 0,
            "trade_size": 0.0,
            "cost": 0.0,
            "weighted_days": 0.0,
            "sector_score_w": 0.0,
            "sector_mv": 0.0,
            "sector": None,
        }
        for hid, lab, _lo, _hi in HORIZONS
    }
    buckets["not_covered"] = {
        "id": "not_covered",
        "label": "Not Covered",
        "market_value": 0.0,
        "positions": 0,
        "trade_size": 0.0,
        "cost": 0.0,
        "weighted_days": 0.0,
        "sector_score_w": 0.0,
        "sector_mv": 0.0,
        "sector": None,
    }

    total_mv = 0.0
    total_edv = 0.0
    total_cost = 0.0
    weighted_days = 0.0
    day_weight = 0.0
    vol_w = 0.0
    vol_mv = 0.0
    spread_w = 0.0
    spread_mv = 0.0
    score_w = 0.0
    score_mv = 0.0
    populated = {key: 0 for _name, key, _source in LQA_FIELDS}
    security_rows: list[dict[str, Any]] = []

    for position in positions:
        mv = _num(position.get("market_value")) or 0.0
        for _name, key, _source in LQA_FIELDS:
            if position.get(key) not in (None, ""):
                populated[key] += 1
        days = _days_for(position, day_factor, volume_scale, shift)
        hid = _horizon_id(days)
        bucket = buckets[hid]
        spread = _num(position.get("bid_ask_spread"))
        impact = _num(position.get("unif_mkt_imp_cost"))
        unit_cost = spread if spread is not None else impact
        cost = mv * (unit_cost or 0.0) * cost_multiple * cost_factor
        edv = _num(position.get("expected_daily_volume")) or 0.0
        bucket["market_value"] += mv
        bucket["positions"] += 1
        bucket["trade_size"] += edv
        bucket["cost"] += cost
        if days is not None:
            bucket["weighted_days"] += mv * days
            weighted_days += mv * days
            day_weight += mv
        sector = position.get("liquidity_sector")
        score = _num(position.get("sector_score"))
        if score is not None and mv:
            bucket["sector_score_w"] += score * mv
            bucket["sector_mv"] += mv
            score_w += score * mv
            score_mv += mv
        if sector and bucket["sector"] is None:
            bucket["sector"] = str(sector)
        vol = _num(position.get("price_volatility"))
        if vol is not None and mv:
            vol_w += vol * mv
            vol_mv += mv
        if spread is not None and mv:
            spread_w += spread * mv
            spread_mv += mv
        total_mv += mv
        total_edv += edv
        total_cost += cost
        security_rows.append(
            {
                "security_code": str(position.get("security_code") or ""),
                "security_name": str(position.get("security_name") or position.get("security_code") or ""),
                "market_value": _round(mv, 2),
                "mv_weight_pct": None,
                "liq_horizon_days": _round(days, 1),
                "hk_sfc_port_lqdty_class": position.get("hk_sfc_port_lqdty_class"),
                "scenario_lqdty_class": _class_for_days(days),
                "unif_mkt_imp_cost": _round(impact if impact is not None else unit_cost, 6),
                "bid_ask_spread": _round(spread, 6),
                "bid_ask_bps": _round((spread or 0.0) * 10000.0, 2) if spread is not None else None,
                "expected_daily_volume": _round(edv, 2),
                "sector_score": _round(score, 2) if score is not None else None,
                "liquidity_sector": str(sector) if sector else None,
                "price_volatility": _round(vol, 6) if vol is not None else None,
                "cost": None,
                "horizon_bucket": buckets[hid]["label"],
            }
        )

    redeem = max(0.0, min(float(redemption_pct), 100.0)) / 100.0
    for row in security_rows:
        mv = row["market_value"] or 0.0
        row["mv_weight_pct"] = _round(mv / total_mv * 100.0, 2) if total_mv else 0.0
        unit = row["unif_mkt_imp_cost"] if row["unif_mkt_imp_cost"] is not None else row["bid_ask_spread"]
        row["cost"] = _round(mv * (unit or 0.0) * cost_multiple * cost_factor * redeem, 2)
    security_rows.sort(
        key=lambda row: (
            row["liq_horizon_days"] is None,
            -(row["liq_horizon_days"] or 0),
            -(row["market_value"] or 0),
        )
    )
    nominal = total_mv * redeem
    redeem_cost = total_cost * redeem
    annual = (vol_w / vol_mv) if vol_mv else None
    if annual is not None and annual <= 1:
        annual *= 100.0
    daily = (annual / (252 ** 0.5)) if annual is not None else None
    bid_ask_bps = (spread_w / spread_mv * 10000.0) if spread_mv else None

    horizons = []
    for bucket in buckets.values():
        mv = bucket["market_value"]
        horizons.append(
            {
                "id": bucket["id"],
                "label": bucket["label"],
                "market_value": _round(mv, 2),
                "mv_weight_pct": _round(mv / total_mv * 100.0, 1) if total_mv else 0.0,
                "positions": bucket["positions"],
                "trade_size": _round(bucket["trade_size"], 2),
                "liq_horizon_days": _round(bucket["weighted_days"] / mv, 1) if mv else None,
                "sector_score": _round(bucket["sector_score_w"] / bucket["sector_mv"], 2) if bucket["sector_mv"] else None,
                "sector": bucket["sector"],
                "cost": _round(bucket["cost"] * redeem, 2),
            }
        )

    field_coverage = [
        {
            "field": name,
            "exists": True,
            "populated": populated[key],
            "proxy": source,
        }
        for name, key, source in LQA_FIELDS
    ]
    return {
        "scenario": {"code": code, "label": label},
        "scenarios": [{"code": item[0], "label": item[1]} for item in SCENARIOS],
        "assumptions": {
            "redemption_pct": round(float(redemption_pct), 2),
            "target_cost": "Bid-Ask",
            "cost_multiple": float(cost_multiple),
            "include_current_day": bool(include_current_day),
        },
        "overview": {
            "market_value": _round(total_mv, 2),
            "positions": len(positions),
            "bid_ask_bps": _round(bid_ask_bps, 2),
            "annual_volatility": _round(annual, 2),
            "daily_volatility": _round(daily, 4),
            "pct_of_edv": _round(total_mv / total_edv * 100.0, 2) if total_edv else None,
            "liq_horizon_days": _round(weighted_days / day_weight, 1) if day_weight else None,
            "global_score": _round(score_w / score_mv, 2) if score_mv else None,
        },
        "redemption": {
            "nominal": _round(nominal, 2),
            "cost": _round(redeem_cost, 2),
            "value": _round(nominal - redeem_cost, 2),
            "residual_market_value": _round(total_mv - nominal, 2),
        },
        "horizons": horizons,
        "securities": security_rows,
        "not_covered_positions": buckets["not_covered"]["positions"],
        "lqa_fields": field_coverage,
        "lqa_present_count": len(LQA_FIELDS),
        "lqa_populated_fields": sum(1 for item in field_coverage if item["populated"]),
    }
