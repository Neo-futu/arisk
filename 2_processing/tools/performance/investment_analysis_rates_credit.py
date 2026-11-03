"""Rates and credit sensitivity calculations."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .investment_analysis_common import _date_value, _number

# 投资级（IG）：BBB- / Baa3 及以上；其余含 NR 视为低于投资级（统一到 SP 符号后判定）
_INVESTMENT_GRADE = {
    "AAA+", "AAA", "AAA-", "AA+", "AA", "AA-",
    "A+", "A", "A-", "BBB+", "BBB", "BBB-",
}
_RATING_ORDER = [
    "AAA+", "AAA", "AAA-", "AA+", "AA", "AA-",
    "A+", "A", "A-", "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-", "B+", "B", "B-",
    "CCC", "CC", "C", "D", "NR",
]

# 标普/惠誉/内地长期符号 ↔ 穆迪（粗映射，仅对照量级；非官方换算）
_SP_TO_MOODY = {
    "AAA": "Aaa",
    "AA+": "Aa1",
    "AA": "Aa2",
    "AA-": "Aa3",
    "A+": "A1",
    "A": "A2",
    "A-": "A3",
    "BBB+": "Baa1",
    "BBB": "Baa2",
    "BBB-": "Baa3",
    "BB+": "Ba1",
    "BB": "Ba2",
    "BB-": "Ba3",
    "B+": "B1",
    "B": "B2",
    "B-": "B3",
    "CCC+": "Caa1",
    "CCC": "Caa2",
    "CCC-": "Caa3",
    "CC": "Ca",
    "C": "C",
    "D": "C",
}
_MOODY_TO_SP = {moody.upper(): sp for sp, moody in _SP_TO_MOODY.items()}
_MOODY_DISPLAY = {sp: moody for sp, moody in _SP_TO_MOODY.items()}
_MOODY_DISPLAY.update({moody.upper(): moody for moody in _SP_TO_MOODY.values()})

# 评级来源：国内（中诚信/联合）/ 国际三大 / 内评（不再使用中债资信）
_DOMESTIC_AGENCIES = frozenset({"CSCI", "LIANHE"})
_FOREIGN_AGENCIES = frozenset({"SP", "MOODY", "FITCH"})
_AGENCY_ALIASES = {
    "all": None,
    "domestic": _DOMESTIC_AGENCIES,
    "foreign": _FOREIGN_AGENCIES,
    "sp": frozenset({"SP"}),
    "moody": frozenset({"MOODY"}),
    "fitch": frozenset({"FITCH"}),
    "csci": frozenset({"CSCI"}),
    "lianhe": frozenset({"LIANHE"}),
    "internal": frozenset({"INTERNAL"}),
}
_RATING_SOURCE_OPTIONS = [
    {"id": "all", "group": "all", "label_zh": "全部（不区分机构）"},
    {"id": "domestic", "group": "domestic", "label_zh": "国内评级（中诚信/联合）"},
    {"id": "csci", "group": "domestic", "label_zh": "中诚信 CSCI"},
    {"id": "lianhe", "group": "domestic", "label_zh": "联合资信 LIANHE"},
    {"id": "foreign", "group": "foreign", "label_zh": "国际评级（标普/穆迪/惠誉）"},
    {"id": "sp", "group": "foreign", "label_zh": "标普 S&P"},
    {"id": "moody", "group": "foreign", "label_zh": "穆迪 Moody's"},
    {"id": "fitch", "group": "foreign", "label_zh": "惠誉 Fitch"},
    {"id": "internal", "group": "internal", "label_zh": "内部评级"},
]

# 按券统一列示：中诚信 / 联合 / 标普 / 穆迪 / 惠誉 / 内评（无汇总列、无中债资信）
_AGENCY_COLUMNS = ("CSCI", "LIANHE", "SP", "MOODY", "FITCH", "INTERNAL")
_AGENCY_COLUMN_KEYS = {
    "CSCI": "csci",
    "LIANHE": "lianhe",
    "SP": "sp",
    "MOODY": "moody",
    "FITCH": "fitch",
    "INTERNAL": "internal",
}

# 各机构长期评级档位对照（粗映射；内地↔国际无官方换算）
_RATING_SCALE_LEGEND = [
    {"band": "最高", "grade": "investment", "domestic": "AAA", "sp_fitch": "AAA", "moody": "Aaa"},
    {"band": "很强+", "grade": "investment", "domestic": "AA+", "sp_fitch": "AA+", "moody": "Aa1"},
    {"band": "很强", "grade": "investment", "domestic": "AA", "sp_fitch": "AA", "moody": "Aa2"},
    {"band": "很强-", "grade": "investment", "domestic": "AA-", "sp_fitch": "AA-", "moody": "Aa3"},
    {"band": "较强+", "grade": "investment", "domestic": "A+", "sp_fitch": "A+", "moody": "A1"},
    {"band": "较强", "grade": "investment", "domestic": "A", "sp_fitch": "A", "moody": "A2"},
    {"band": "较强-", "grade": "investment", "domestic": "A-", "sp_fitch": "A-", "moody": "A3"},
    {"band": "一般+", "grade": "investment", "domestic": "BBB+", "sp_fitch": "BBB+", "moody": "Baa1"},
    {"band": "一般", "grade": "investment", "domestic": "BBB", "sp_fitch": "BBB", "moody": "Baa2"},
    {"band": "投资级下沿", "grade": "investment", "domestic": "BBB-", "sp_fitch": "BBB-", "moody": "Baa3"},
    {"band": "投机级起", "grade": "speculative", "domestic": "BB+", "sp_fitch": "BB+", "moody": "Ba1"},
    {"band": "投机", "grade": "speculative", "domestic": "BB", "sp_fitch": "BB", "moody": "Ba2"},
    {"band": "投机-", "grade": "speculative", "domestic": "BB-", "sp_fitch": "BB-", "moody": "Ba3"},
    {"band": "高风险+", "grade": "speculative", "domestic": "B+", "sp_fitch": "B+", "moody": "B1"},
    {"band": "高风险", "grade": "speculative", "domestic": "B", "sp_fitch": "B", "moody": "B2"},
    {"band": "高风险-", "grade": "speculative", "domestic": "B-", "sp_fitch": "B-", "moody": "B3"},
    {"band": "很高违约风险", "grade": "speculative", "domestic": "CCC", "sp_fitch": "CCC", "moody": "Caa2"},
    {"band": "接近违约", "grade": "speculative", "domestic": "CC/C", "sp_fitch": "CC/C", "moody": "Ca/C"},
]


def _canonical_token(raw: object) -> str:
    """去空格并大写，便于查表。"""
    return str(raw or "").strip().replace(" ", "").upper()


def _to_sp_symbol(raw: object) -> str | None:
    """转为标普/惠誉/内地长期符号（AAA、AA+…）；短期 A-1 等保持原样。"""
    original = str(raw or "").strip()
    if not original:
        return None
    # 短期档仅识别带连字符：A-1 / A-1+ / A-2 / A-3（勿把穆迪 A1 当成短期）
    short = original.upper().replace(" ", "")
    if re.fullmatch(r"A-[123]\+?", short):
        return short
    token = _canonical_token(original)
    if token == "NR":
        return "NR"
    if token in _MOODY_TO_SP:
        return _MOODY_TO_SP[token]
    if token in _SP_TO_MOODY:
        return token
    if re.fullmatch(r"[A-D]{1,3}[+-]?", token):
        return token
    return original


def _to_moody_symbol(raw: object) -> str | None:
    """转为穆迪长期符号（Aaa、Aa1、Baa2…）；粗映射自 SP/内地符号。"""
    original = str(raw or "").strip()
    if not original:
        return None
    token = _canonical_token(original)
    if token == "NR":
        return "NR"
    if token in _MOODY_DISPLAY:
        return _MOODY_DISPLAY[token]
    sp = _to_sp_symbol(original)
    if not sp or sp == "NR":
        return sp
    return _SP_TO_MOODY.get(sp, sp)


def _agency_display_rating(agency: str, raw: object) -> str | None:
    """按机构体系输出展示符号：穆迪用 Aaa/Aa1；其余用 AAA/AA+。"""
    text_v = str(raw or "").strip()
    if not text_v:
        return None
    if (agency or "").strip().upper() == "MOODY":
        return _to_moody_symbol(text_v)
    return _to_sp_symbol(text_v) or text_v


def _normalize_rating(raw: object) -> str:
    """统一到 SP 符号，便于 IG 判定与排序（不用于多机构列展示）。"""
    return _to_sp_symbol(raw) or "NR"


def _is_investment_grade(rating: str) -> bool:
    r = _normalize_rating(rating)
    if r in _INVESTMENT_GRADE:
        return True
    if r in {"AAA", "AA", "A", "BAA", "BBB"}:
        return True
    return False


def _rating_sort_key(rating: str) -> tuple[int, str]:
    r = _normalize_rating(rating)
    try:
        return (_RATING_ORDER.index(r), r)
    except ValueError:
        return (len(_RATING_ORDER), r)


def _build_rating_distribution(
    rating_mv: dict[str, float],
    total_bond_mv: float,
) -> dict[str, Any]:
    rows = [
        {
            "rating": rating,
            "market_value": value,
            "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
            "is_investment_grade": _is_investment_grade(rating),
        }
        for rating, value in sorted(rating_mv.items(), key=lambda item: _rating_sort_key(item[0]))
    ]
    ig_mv = sum(v for r, v in rating_mv.items() if _is_investment_grade(r))
    below_ig_mv = total_bond_mv - ig_mv
    return {
        "distribution": rows,
        "investment_grade_pct": (ig_mv / total_bond_mv * 100.0) if total_bond_mv else None,
        "below_investment_grade_pct": (below_ig_mv / total_bond_mv * 100.0) if total_bond_mv else None,
    }


def _normalize_source(raw: str | None) -> str:
    key = str(raw or "all").strip().lower()
    return key if key in _AGENCY_ALIASES else "all"


def _agency_of(item: dict[str, Any]) -> str:
    return str(item.get("rating_agency") or "NR").strip().upper() or "NR"


def _bond_matches_source(item: dict[str, Any], source: str) -> bool:
    agencies = _AGENCY_ALIASES.get(source)
    if agencies is None:
        return True
    return _agency_of(item) in agencies


def _empty_agency_map() -> dict[str, str | None]:
    return {key: None for key in _AGENCY_COLUMN_KEYS.values()}


def _apply_agency_symbols(agency_map: dict[str, str | None]) -> dict[str, str | None]:
    """把各机构列校正为该机构惯用符号。"""
    out = dict(agency_map)
    for agency, key in _AGENCY_COLUMN_KEYS.items():
        if out.get(key):
            out[key] = _agency_display_rating(agency, out[key])
    return out


def _build_bond_agency_rating_rows(
    bonds: list[dict[str, Any]],
    agency_rows: list[dict[str, Any]],
    total_bond_mv: float,
) -> list[dict[str, Any]]:
    """按券展开多家机构主体/债项评级，供利率信用 Tab 统一列示。"""
    by_security: dict[str, dict[str, dict[str, str | None]]] = defaultdict(
        lambda: {"issuer": _empty_agency_map(), "debt": _empty_agency_map()}
    )
    for row in agency_rows:
        code = str(row.get("security_code") or "").strip()
        agency = str(row.get("rating_agency") or "").strip().upper()
        key = _AGENCY_COLUMN_KEYS.get(agency)
        if not code or not key:
            continue
        issuer = _agency_display_rating(agency, row.get("issuer_rating"))
        debt = _agency_display_rating(agency, row.get("debt_rating"))
        if issuer:
            by_security[code]["issuer"][key] = issuer
        if debt:
            by_security[code]["debt"][key] = debt

    # 无多机构表时，回退 balance_bond 单机构 + 内评（按机构体系转符号）
    for item in bonds:
        code = str(item.get("security_code") or "").strip()
        if not code:
            continue
        bucket = by_security[code]
        agency = _agency_of(item)
        agency_key = _AGENCY_COLUMN_KEYS.get(agency)
        if agency_key and agency_key != "internal":
            if not bucket["issuer"].get(agency_key):
                issuer = _agency_display_rating(agency, item.get("issuer_rating"))
                if issuer:
                    bucket["issuer"][agency_key] = issuer
            if not bucket["debt"].get(agency_key):
                debt = _agency_display_rating(agency, item.get("debt_rating"))
                if debt:
                    bucket["debt"][agency_key] = debt
        internal = _agency_display_rating("INTERNAL", item.get("internal_rating"))
        if internal:
            bucket["issuer"]["internal"] = bucket["issuer"].get("internal") or internal
            bucket["debt"]["internal"] = bucket["debt"].get("internal") or internal

    rows: list[dict[str, Any]] = []
    for item in bonds:
        code = str(item.get("security_code") or "").strip()
        if not code:
            continue
        mv = _number(item.get("market_value"))
        issuer_map = _apply_agency_symbols(by_security[code]["issuer"])
        debt_map = _apply_agency_symbols(by_security[code]["debt"])
        rows.append(
            {
                "security_code": code,
                "security_name": item.get("security_name"),
                "issuer_name": item.get("issuer_name"),
                "market_value": mv,
                "weight_pct": mv / total_bond_mv * 100.0 if total_bond_mv else 0.0,
                "issuer_ratings": issuer_map,
                "debt_ratings": debt_map,
            }
        )
    rows.sort(key=lambda row: row["market_value"], reverse=True)
    return rows


async def compute_rates_credit_sensitivity(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    *,
    rating_source: str = "all",
) -> dict[str, Any]:
    source = _normalize_source(rating_source)
    nav_result = await db.execute(
        text(
            """
            SELECT net_asset
            FROM fsi.balance_portfolio_nav
            WHERE port_id = :fund_id AND evaluate_date <= :as_of_date
            ORDER BY evaluate_date DESC
            LIMIT 1
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    nav = _number(nav_result.scalar_one_or_none())

    bonds_result = await db.execute(
        text(
            """
            SELECT security_code,
                   security_name,
                   COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
                   issuer_rating,
                   debt_rating,
                   internal_rating,
                   COALESCE(rating_agency::text, 'NR') AS rating_agency,
                   COALESCE(debt_rating, issuer_rating, 'NR') AS rating,
                   maturity_date,
                   COALESCE(duration, 0) AS duration,
                   COALESCE(ytm, 0) AS ytm,
                   COALESCE(market_value_base, market_value, 0) AS market_value
            FROM fsi.balance_bond
            WHERE port_id = :fund_id
              AND evaluate_date = :as_of_date
            """
        ),
        {"fund_id": fund_id, "as_of_date": as_of_date},
    )
    bonds = [dict(row) for row in bonds_result.mappings().all()]
    agency_rows: list[dict[str, Any]] = []
    try:
        agency_result = await db.execute(
            text(
                """
                SELECT security_code,
                       rating_agency::text AS rating_agency,
                       issuer_rating,
                       debt_rating
                FROM fsi.balance_bond_agency_rating
                WHERE port_id = :fund_id
                  AND evaluate_date = :as_of_date
                """
            ),
            {"fund_id": fund_id, "as_of_date": as_of_date},
        )
        agency_rows = [dict(row) for row in agency_result.mappings().all()]
    except Exception:
        # 未执行 027 迁移时回退到 balance_bond 单机构列
        await db.rollback()
        agency_rows = []
    total_bond_mv = sum(_number(item["market_value"]) for item in bonds)
    bond_agency_rating_rows = _build_bond_agency_rating_rows(bonds, agency_rows, total_bond_mv)
    weighted_duration = (
        sum(_number(item["market_value"]) * _number(item["duration"]) for item in bonds) / total_bond_mv
        if total_bond_mv
        else None
    )

    krd_buckets: dict[str, float] = {"1M": 0.0, "3M": 0.0, "6M": 0.0, "1Y": 0.0, "1Y+": 0.0}
    issuer_mv: dict[str, float] = defaultdict(float)
    blended_rating_mv: dict[str, float] = defaultdict(float)
    issuer_rating_mv: dict[str, float] = defaultdict(float)
    debt_rating_mv: dict[str, float] = defaultdict(float)
    portfolio_dv01 = 0.0
    portfolio_cs01 = 0.0
    agency_counts: dict[str, int] = defaultdict(int)
    matched_mv = 0.0
    matched_count = 0

    for item in bonds:
        mv = _number(item["market_value"])
        duration_years = _number(item["duration"])
        maturity_date = item.get("maturity_date")
        days_to_maturity = 9999
        if maturity_date is not None:
            try:
                days_to_maturity = max((_date_value(maturity_date) - as_of_date).days, 0)
            except Exception:
                days_to_maturity = 9999

        if days_to_maturity <= 30:
            bucket = "1M"
        elif days_to_maturity <= 90:
            bucket = "3M"
        elif days_to_maturity <= 180:
            bucket = "6M"
        elif days_to_maturity <= 365:
            bucket = "1Y"
        else:
            bucket = "1Y+"
        krd_buckets[bucket] += mv * duration_years

        issuer_mv[str(item["issuer_name"])] += mv
        portfolio_dv01 += mv * duration_years * 0.0001
        # 没有完整 spread duration 时，使用 duration 的 80% 作保守代理
        portfolio_cs01 += mv * duration_years * 0.8 * 0.0001

        agency_counts[_agency_of(item)] += 1
        if not _bond_matches_source(item, source):
            continue
        matched_mv += mv
        matched_count += 1

        if source == "internal":
            rating = _agency_display_rating("INTERNAL", item.get("internal_rating")) or "NR"
            issuer_rating_mv[rating] += mv
            debt_rating_mv[rating] += mv
            blended_rating_mv[rating] += mv
        elif source == "moody":
            # 穆迪来源：分布桶用 Aaa/Aa1，勿写成 AAA/AA+
            issuer_r = _agency_display_rating("MOODY", item.get("issuer_rating")) or "NR"
            debt_r = _agency_display_rating("MOODY", item.get("debt_rating")) or "NR"
            blended_r = _agency_display_rating("MOODY", item.get("rating")) or "NR"
            issuer_rating_mv[issuer_r] += mv
            debt_rating_mv[debt_r] += mv
            blended_rating_mv[blended_r] += mv
        else:
            # 国内 / 标普 / 惠誉 / 全部：统一 SP·内地符号，避免 Aaa 与 AAA 拆成两档
            issuer_r = _normalize_rating(item.get("issuer_rating"))
            debt_r = _normalize_rating(item.get("debt_rating"))
            blended_r = _normalize_rating(item.get("rating"))
            issuer_rating_mv[issuer_r] += mv
            debt_rating_mv[debt_r] += mv
            blended_rating_mv[blended_r] += mv

    denom = matched_mv if source != "all" else total_bond_mv
    issuer_rows = [
        {
            "issuer": issuer,
            "market_value": value,
            "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
        }
        for issuer, value in issuer_mv.items()
    ]
    issuer_rows.sort(key=lambda row: row["market_value"], reverse=True)
    hhi = sum((row["weight_pct"] / 100.0) ** 2 for row in issuer_rows) * 10000 if issuer_rows else 0.0

    blended = _build_rating_distribution(blended_rating_mv, denom)
    issuer_rt = _build_rating_distribution(issuer_rating_mv, denom)
    debt_rt = _build_rating_distribution(debt_rating_mv, denom)

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "net_asset": nav,
        "total_bond_market_value": total_bond_mv,
        "bond_exposure_pct_nav": total_bond_mv / nav * 100.0 if nav else None,
        "weighted_duration_years": weighted_duration,
        "portfolio_dv01": portfolio_dv01,
        "portfolio_cs01": portfolio_cs01,
        "krd_buckets": [
            {
                "bucket": key,
                "duration_weighted_mv": value,
                "weight_pct_bond": value / sum(krd_buckets.values()) * 100.0 if sum(krd_buckets.values()) else 0.0,
            }
            for key, value in krd_buckets.items()
        ],
        "issuer_concentration": {
            "hhi": hhi,
            "top_issuers": issuer_rows[:10],
        },
        # 兼容旧前端：合成评级（债项优先，缺省主体）
        "rating_distribution": blended["distribution"],
        "investment_grade_pct": blended["investment_grade_pct"],
        "below_investment_grade_pct": blended["below_investment_grade_pct"],
        # 主体 / 债项分列
        "issuer_rating_distribution": issuer_rt["distribution"],
        "debt_rating_distribution": debt_rt["distribution"],
        "issuer_investment_grade_pct": issuer_rt["investment_grade_pct"],
        "issuer_below_investment_grade_pct": issuer_rt["below_investment_grade_pct"],
        "debt_investment_grade_pct": debt_rt["investment_grade_pct"],
        "debt_below_investment_grade_pct": debt_rt["below_investment_grade_pct"],
        "bond_count": len(bonds),
        "rating_source": source,
        "rating_source_options": _RATING_SOURCE_OPTIONS,
        "rating_matched_bond_count": matched_count,
        "rating_matched_market_value": matched_mv,
        "rating_agency_counts": dict(agency_counts),
        # 按券多家机构统一列示（主体 / 债项）
        "bond_agency_rating_columns": list(_AGENCY_COLUMNS),
        "bond_agency_rating_rows": bond_agency_rating_rows,
        # 各机构投资级/投机级档位与符号对照（粗映射说明）
        "rating_scale_legend": _RATING_SCALE_LEGEND,
        "rating_scale_note": (
            "内地（中诚信/联合）与标普/惠誉同用 AAA·AA+ 符号；穆迪用 Aaa·Aa1。"
            "内地↔国际无官方换算，本表仅为量级对照；投资级下沿为 BBB- / Baa3，BB+ / Ba1 起为投机级。"
        ),
    }
