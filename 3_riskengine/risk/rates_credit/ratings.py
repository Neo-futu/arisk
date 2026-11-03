"""评级符号、投资级判定、机构对照（RiskEngine 独立实现）。

不依赖 2_processing。投资级下沿 BBB- / Baa3；穆迪与 SP/内地为粗映射，非官方换算。
"""
from __future__ import annotations

import re
from typing import Any

INVESTMENT_GRADE = {
    "AAA+",
    "AAA",
    "AAA-",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
}

RATING_ORDER = [
    "AAA+",
    "AAA",
    "AAA-",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC",
    "CC",
    "C",
    "D",
    "NR",
]

SP_TO_MOODY = {
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
MOODY_TO_SP = {moody.upper(): sp for sp, moody in SP_TO_MOODY.items()}
MOODY_DISPLAY = {sp: moody for sp, moody in SP_TO_MOODY.items()}
MOODY_DISPLAY.update({moody.upper(): moody for moody in SP_TO_MOODY.values()})

DOMESTIC_AGENCIES = frozenset({"CSCI", "LIANHE"})
FOREIGN_AGENCIES = frozenset({"SP", "MOODY", "FITCH"})
AGENCY_ALIASES: dict[str, frozenset[str] | None] = {
    "all": None,
    "domestic": DOMESTIC_AGENCIES,
    "foreign": FOREIGN_AGENCIES,
    "sp": frozenset({"SP"}),
    "moody": frozenset({"MOODY"}),
    "fitch": frozenset({"FITCH"}),
    "csci": frozenset({"CSCI"}),
    "lianhe": frozenset({"LIANHE"}),
    "internal": frozenset({"INTERNAL"}),
}
RATING_SOURCE_OPTIONS = [
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

AGENCY_COLUMNS = ("CSCI", "LIANHE", "SP", "MOODY", "FITCH", "INTERNAL")
AGENCY_COLUMN_KEYS = {
    "CSCI": "csci",
    "LIANHE": "lianhe",
    "SP": "sp",
    "MOODY": "moody",
    "FITCH": "fitch",
    "INTERNAL": "internal",
}

RATING_SCALE_LEGEND = [
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

RATING_SCALE_NOTE = (
    "内地（中诚信/联合）与标普/惠誉同用 AAA·AA+ 符号；穆迪用 Aaa·Aa1。"
    "内地↔国际无官方换算，本表仅为量级对照；投资级下沿为 BBB- / Baa3，BB+ / Ba1 起为投机级。"
)

# 页面期限结构分桶（按剩余期限天数，非 FinancePy 关键利率久期）
MATURITY_BUCKETS = ("1M", "3M", "6M", "1Y", "1Y+")


def canonical_token(raw: object) -> str:
    return str(raw or "").strip().replace(" ", "").upper()


def to_sp_symbol(raw: object) -> str | None:
    original = str(raw or "").strip()
    if not original:
        return None
    short = original.upper().replace(" ", "")
    if re.fullmatch(r"A-[123]\+?", short):
        return short
    token = canonical_token(original)
    if token == "NR":
        return "NR"
    if token in MOODY_TO_SP:
        return MOODY_TO_SP[token]
    if token in SP_TO_MOODY:
        return token
    if re.fullmatch(r"[A-D]{1,3}[+-]?", token):
        return token
    return original


def to_moody_symbol(raw: object) -> str | None:
    original = str(raw or "").strip()
    if not original:
        return None
    token = canonical_token(original)
    if token == "NR":
        return "NR"
    if token in MOODY_DISPLAY:
        return MOODY_DISPLAY[token]
    sp = to_sp_symbol(original)
    if not sp or sp == "NR":
        return sp
    return SP_TO_MOODY.get(sp, sp)


def agency_display_rating(agency: str, raw: object) -> str | None:
    text_v = str(raw or "").strip()
    if not text_v:
        return None
    if (agency or "").strip().upper() == "MOODY":
        return to_moody_symbol(text_v)
    return to_sp_symbol(text_v) or text_v


def normalize_rating(raw: object) -> str:
    return to_sp_symbol(raw) or "NR"


def is_investment_grade(rating: str) -> bool:
    r = normalize_rating(rating)
    return r in INVESTMENT_GRADE or r in {"AAA", "AA", "A", "BAA", "BBB"}


def rating_sort_key(rating: str) -> tuple[int, str]:
    r = normalize_rating(rating)
    try:
        return (RATING_ORDER.index(r), r)
    except ValueError:
        return (len(RATING_ORDER), r)


def normalize_source(raw: str | None) -> str:
    key = str(raw or "all").strip().lower()
    return key if key in AGENCY_ALIASES else "all"


def agency_of(item: dict[str, Any]) -> str:
    return str(item.get("rating_agency") or "NR").strip().upper() or "NR"


def bond_matches_source(item: dict[str, Any], source: str) -> bool:
    agencies = AGENCY_ALIASES.get(source)
    if agencies is None:
        return True
    return agency_of(item) in agencies


def empty_agency_map() -> dict[str, str | None]:
    return {key: None for key in AGENCY_COLUMN_KEYS.values()}


def apply_agency_symbols(agency_map: dict[str, str | None]) -> dict[str, str | None]:
    out = dict(agency_map)
    for agency, key in AGENCY_COLUMN_KEYS.items():
        if out.get(key):
            out[key] = agency_display_rating(agency, out[key])
    return out


def build_rating_distribution(
    rating_mv: dict[str, float],
    total_bond_mv: float,
) -> dict[str, Any]:
    rows = [
        {
            "rating": rating,
            "market_value": value,
            "weight_pct": value / total_bond_mv * 100.0 if total_bond_mv else 0.0,
            "is_investment_grade": is_investment_grade(rating),
        }
        for rating, value in sorted(rating_mv.items(), key=lambda item: rating_sort_key(item[0]))
    ]
    ig_mv = sum(v for r, v in rating_mv.items() if is_investment_grade(r))
    below = total_bond_mv - ig_mv
    return {
        "distribution": rows,
        "investment_grade_pct": (ig_mv / total_bond_mv * 100.0) if total_bond_mv else None,
        "below_investment_grade_pct": (below / total_bond_mv * 100.0) if total_bond_mv else None,
    }


def maturity_bucket(days_to_maturity: float) -> str:
    if days_to_maturity <= 30:
        return "1M"
    if days_to_maturity <= 90:
        return "3M"
    if days_to_maturity <= 180:
        return "6M"
    if days_to_maturity <= 365:
        return "1Y"
    return "1Y+"
