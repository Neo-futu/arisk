"""投资风险 · 利率与信用敏感度 Tab 业务模块。

页面对应 ``/investment-risk/indicators`` → 利率信用域。业务能力（非 UI）：

1. **债券账本** — 市值、只数、占 NAV
2. **利率/信用敏感度** — 加权久期、DV01、CS01
3. **期限结构分桶** — 1M/3M/6M/1Y/1Y+（剩余期限 × 久期加权）
4. **评级分布** — 主体/债项投资级%与占比明细
5. **按券多家机构评级** — 中诚信/联合/标普/穆迪/惠誉/内评
6. **评级等级对照** — 投资级/投机级符号表
7. **发行人集中度 Top10** — HHI + 前十大发行人

模型相对独立：本包不读报表层、不 import 2_processing；持仓与多机构评级经
snapshot / ``meta.agency_rows`` 注入。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Mapping, Sequence

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ...instruments.classify import FIXED_INCOME, issuer_name
from . import ratings as R

BUSINESS_MODULES = (
    "bond_book",
    "sensitivity",
    "krd_buckets",
    "rating_distribution",
    "bond_agency_ratings",
    "rating_scale",
    "issuer_concentration",
)


def _meta(position: Any) -> dict[str, Any]:
    return dict(getattr(position, "metadata", None) or {})


def _is_bond_like(position: Any) -> bool:
    klass = str(getattr(position, "asset_class", "") or "").upper()
    # 债、CD、以及债基 ETF（页面样例含债券 ETF）
    if klass in FIXED_INCOME:
        return True
    if klass in {"ETF", "FUND"}:
        meta = _meta(position)
        return str(meta.get("fund_asset_class") or meta.get("underlying") or "").upper() in {
            "BOND",
            "FIXED_INCOME",
            "FI",
        } or bool(meta.get("treat_as_bond"))
    return False


def _bond_items(snapshot: Any, meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    if meta.get("bonds"):
        return [dict(row) for row in meta["bonds"]]
    rows: list[dict[str, Any]] = []
    for position in getattr(snapshot, "positions", ()) or ():
        if not _is_bond_like(position):
            continue
        m = _meta(position)
        rows.append(
            {
                "security_code": str(getattr(position, "security_code", "") or ""),
                "security_name": str(getattr(position, "security_name", "") or ""),
                "issuer_name": str(m.get("issuer") or m.get("issuer_name") or issuer_name(position)),
                "issuer_rating": m.get("issuer_rating") or m.get("rating"),
                "debt_rating": m.get("debt_rating") or m.get("rating"),
                "internal_rating": m.get("internal_rating"),
                "rating_agency": m.get("rating_agency") or "SP",
                "rating": m.get("debt_rating") or m.get("issuer_rating") or m.get("rating") or "NR",
                "maturity_date": getattr(position, "maturity_date", None) or m.get("maturity_date"),
                "duration": float(getattr(position, "duration", 0.0) or m.get("duration") or 0.0),
                "ytm": float(getattr(position, "ytm", 0.0) or m.get("ytm") or 0.0),
                "market_value": float(getattr(position, "market_value_base", 0.0) or 0.0),
                "agency_ratings": m.get("agency_ratings") or {},
            }
        )
    return rows


def _days_to_maturity(item: Mapping[str, Any], as_of: date) -> float:
    maturity = item.get("maturity_date")
    if maturity is None:
        # 无到期日时用久期年 × 365 近似
        return max(float(item.get("duration") or 0.0) * 365.0, 9999.0)
    if isinstance(maturity, str):
        maturity = date.fromisoformat(maturity[:10])
    if not isinstance(maturity, date):
        return 9999.0
    return float(max((maturity - as_of).days, 0))


def build_bond_agency_rating_rows(
    bonds: Sequence[Mapping[str, Any]],
    agency_rows: Sequence[Mapping[str, Any]],
    total_bond_mv: float,
) -> list[dict[str, Any]]:
    by_security: dict[str, dict[str, dict[str, str | None]]] = defaultdict(
        lambda: {"issuer": R.empty_agency_map(), "debt": R.empty_agency_map()}
    )
    for row in agency_rows:
        code = str(row.get("security_code") or "")
        agency = str(row.get("rating_agency") or "").strip().upper()
        key = R.AGENCY_COLUMN_KEYS.get(agency)
        if not code or not key:
            continue
        issuer = R.agency_display_rating(agency, row.get("issuer_rating"))
        debt = R.agency_display_rating(agency, row.get("debt_rating"))
        if issuer:
            by_security[code]["issuer"][key] = issuer
        if debt:
            by_security[code]["debt"][key] = debt

    out: list[dict[str, Any]] = []
    for item in bonds:
        code = str(item.get("security_code") or "")
        mv = float(item.get("market_value") or 0.0)
        # 持仓单机构列回填
        agency = R.agency_of(dict(item))
        agency_key = R.AGENCY_COLUMN_KEYS.get(agency)
        bucket = by_security[code]
        if agency_key and agency_key != "internal":
            if not bucket["issuer"].get(agency_key):
                issuer = R.agency_display_rating(agency, item.get("issuer_rating"))
                if issuer:
                    bucket["issuer"][agency_key] = issuer
            if not bucket["debt"].get(agency_key):
                debt = R.agency_display_rating(agency, item.get("debt_rating"))
                if debt:
                    bucket["debt"][agency_key] = debt
        internal = R.agency_display_rating("INTERNAL", item.get("internal_rating"))
        if internal:
            bucket["issuer"]["internal"] = bucket["issuer"].get("internal") or internal
            bucket["debt"]["internal"] = bucket["debt"].get("internal") or internal
        # metadata.agency_ratings 显式覆盖
        explicit = dict(item.get("agency_ratings") or {})
        for side in ("issuer", "debt"):
            side_map = dict(explicit.get(side) or {})
            for key, value in side_map.items():
                if value:
                    bucket[side][key] = R.agency_display_rating(
                        {v: k for k, v in R.AGENCY_COLUMN_KEYS.items()}.get(key, key.upper()),
                        value,
                    )

        out.append(
            {
                "security_code": code,
                "security_name": item.get("security_name"),
                "issuer_name": item.get("issuer_name"),
                "market_value": mv,
                "weight_pct": mv / total_bond_mv * 100.0 if total_bond_mv else 0.0,
                "issuer_ratings": R.apply_agency_symbols(bucket["issuer"]),
                "debt_ratings": R.apply_agency_symbols(bucket["debt"]),
            }
        )
    out.sort(key=lambda row: abs(float(row["market_value"])), reverse=True)
    return out


def module_bond_book(bonds: Sequence[Mapping[str, Any]], nav: float) -> dict[str, Any]:
    total = sum(float(b.get("market_value") or 0.0) for b in bonds)
    return {
        "module": "bond_book",
        "total_bond_market_value": total,
        "bond_count": len(bonds),
        "bond_exposure_pct_nav": (total / nav * 100.0) if nav else None,
        "net_asset": nav,
    }


def module_sensitivity(bonds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = sum(float(b.get("market_value") or 0.0) for b in bonds)
    if not total:
        return {
            "module": "sensitivity",
            "weighted_duration_years": None,
            "portfolio_dv01": 0.0,
            "portfolio_cs01": 0.0,
            "formula": {
                "duration": "Σ(MV×D)/ΣMV",
                "dv01": "Σ MV×D×0.0001",
                "cs01": "Σ MV×0.8D×0.0001（无 spread duration 时）",
            },
        }
    weighted = sum(float(b.get("market_value") or 0.0) * float(b.get("duration") or 0.0) for b in bonds) / total
    dv01 = sum(float(b.get("market_value") or 0.0) * float(b.get("duration") or 0.0) * 0.0001 for b in bonds)
    cs01 = sum(float(b.get("market_value") or 0.0) * float(b.get("duration") or 0.0) * 0.8 * 0.0001 for b in bonds)
    return {
        "module": "sensitivity",
        "weighted_duration_years": weighted,
        "portfolio_dv01": dv01,
        "portfolio_cs01": cs01,
        "note": {
            "dv01": "利率上升 1bp 时组合市值变动",
            "cs01": "信用利差上升 1bp 时组合市值变动的近似（Spread DV01）",
        },
        "formula": {
            "duration": "Σ(MV×D)/ΣMV",
            "dv01": "Σ MV×D×0.0001",
            "cs01": "Σ MV×0.8D×0.0001",
        },
    }


def module_krd_buckets(bonds: Sequence[Mapping[str, Any]], as_of: date) -> dict[str, Any]:
    buckets: dict[str, float] = {key: 0.0 for key in R.MATURITY_BUCKETS}
    for item in bonds:
        mv = float(item.get("market_value") or 0.0)
        duration = float(item.get("duration") or 0.0)
        bucket = R.maturity_bucket(_days_to_maturity(item, as_of))
        buckets[bucket] += mv * duration
    total = sum(buckets.values())
    rows = [
        {
            "bucket": key,
            "duration_weighted_mv": value,
            "weight_pct_bond": value / total * 100.0 if total else 0.0,
        }
        for key, value in buckets.items()
    ]
    return {
        "module": "krd_buckets",
        "rows": rows,
        "note": "按剩余期限分桶的久期加权市值占比（页面「期限结构分桶」）",
    }


def module_rating_distribution(
    bonds: Sequence[Mapping[str, Any]],
    *,
    source: str = "all",
) -> dict[str, Any]:
    source = R.normalize_source(source)
    total_bond_mv = sum(float(b.get("market_value") or 0.0) for b in bonds)
    issuer_mv: dict[str, float] = defaultdict(float)
    debt_mv: dict[str, float] = defaultdict(float)
    blended_mv: dict[str, float] = defaultdict(float)
    agency_counts: dict[str, int] = defaultdict(int)
    matched_mv = 0.0
    matched_count = 0

    for item in bonds:
        mv = float(item.get("market_value") or 0.0)
        agency_counts[R.agency_of(dict(item))] += 1
        if not R.bond_matches_source(dict(item), source):
            continue
        matched_mv += mv
        matched_count += 1
        if source == "internal":
            rating = R.agency_display_rating("INTERNAL", item.get("internal_rating")) or "NR"
            issuer_mv[rating] += mv
            debt_mv[rating] += mv
            blended_mv[rating] += mv
        elif source == "moody":
            issuer_r = R.agency_display_rating("MOODY", item.get("issuer_rating")) or "NR"
            debt_r = R.agency_display_rating("MOODY", item.get("debt_rating")) or "NR"
            blended_r = R.agency_display_rating("MOODY", item.get("rating")) or "NR"
            issuer_mv[issuer_r] += mv
            debt_mv[debt_r] += mv
            blended_mv[blended_r] += mv
        else:
            issuer_r = R.normalize_rating(item.get("issuer_rating"))
            debt_r = R.normalize_rating(item.get("debt_rating"))
            blended_r = R.normalize_rating(item.get("rating"))
            issuer_mv[issuer_r] += mv
            debt_mv[debt_r] += mv
            blended_mv[blended_r] += mv

    denom = matched_mv if source != "all" else total_bond_mv
    blended = R.build_rating_distribution(blended_mv, denom)
    issuer_rt = R.build_rating_distribution(issuer_mv, denom)
    debt_rt = R.build_rating_distribution(debt_mv, denom)
    return {
        "module": "rating_distribution",
        "rating_source": source,
        "rating_source_options": list(R.RATING_SOURCE_OPTIONS),
        "rating_matched_bond_count": matched_count,
        "rating_matched_market_value": matched_mv,
        "rating_agency_counts": dict(agency_counts),
        "rating_distribution": blended["distribution"],
        "investment_grade_pct": blended["investment_grade_pct"],
        "below_investment_grade_pct": blended["below_investment_grade_pct"],
        "issuer_rating_distribution": issuer_rt["distribution"],
        "debt_rating_distribution": debt_rt["distribution"],
        "issuer_investment_grade_pct": issuer_rt["investment_grade_pct"],
        "issuer_below_investment_grade_pct": issuer_rt["below_investment_grade_pct"],
        "debt_investment_grade_pct": debt_rt["investment_grade_pct"],
        "debt_below_investment_grade_pct": debt_rt["below_investment_grade_pct"],
        "ig_hint": "BBB- / Baa3 及以上",
    }


def module_bond_agency_ratings(
    bonds: Sequence[Mapping[str, Any]],
    agency_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = sum(float(b.get("market_value") or 0.0) for b in bonds)
    rows = build_bond_agency_rating_rows(bonds, agency_rows, total)
    return {
        "module": "bond_agency_ratings",
        "bond_agency_rating_columns": list(R.AGENCY_COLUMNS),
        "rows": rows,
        "count": len(rows),
        "hint": "每只持仓列示：中诚信、联合、标普、穆迪、惠誉、内部评级。内地/标普/惠誉/内评用 AAA·AA+；穆迪用 Aaa·Aa1。",
    }


def module_rating_scale() -> dict[str, Any]:
    return {
        "module": "rating_scale",
        "rating_scale_legend": list(R.RATING_SCALE_LEGEND),
        "rating_scale_note": R.RATING_SCALE_NOTE,
    }


def module_issuer_concentration(bonds: Sequence[Mapping[str, Any]], *, top_n: int = 10) -> dict[str, Any]:
    total = sum(float(b.get("market_value") or 0.0) for b in bonds)
    issuer_mv: dict[str, float] = defaultdict(float)
    for item in bonds:
        issuer_mv[str(item.get("issuer_name") or "UNKNOWN")] += float(item.get("market_value") or 0.0)
    rows = [
        {
            "issuer": issuer,
            "market_value": value,
            "weight_pct": value / total * 100.0 if total else 0.0,
        }
        for issuer, value in sorted(issuer_mv.items(), key=lambda item: item[1], reverse=True)
    ]
    hhi = sum((row["weight_pct"] / 100.0) ** 2 for row in rows) * 10_000.0 if rows else 0.0
    return {
        "module": "issuer_concentration",
        "hhi": hhi,
        "top_issuers": rows[:top_n],
        "issuer_count": len(rows),
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    rating_source: str = "all",
    top_n: int = 10,
) -> dict[str, Any]:
    """利率信用 Tab 七大业务模块打包。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    nav = float(info.get("net_asset") or snapshot.net_asset or 0.0)
    as_of = snapshot.as_of_date
    bonds = _bond_items(snapshot, info)
    agency_rows = [dict(row) for row in (info.get("agency_rows") or ())]

    book = module_bond_book(bonds, nav)
    sensitivity = module_sensitivity(bonds)
    krd = module_krd_buckets(bonds, as_of)
    ratings_pack = module_rating_distribution(bonds, source=rating_source)
    agency = module_bond_agency_ratings(bonds, agency_rows)
    scale = module_rating_scale()
    concentration = module_issuer_concentration(bonds, top_n=top_n)

    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/indicators",
        "tab": "rates-credit",
        "fund_id": str(snapshot.fund_id),
        "as_of_date": as_of.isoformat(),
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "bond_book": book,
            "sensitivity": sensitivity,
            "krd_buckets": krd,
            "rating_distribution": ratings_pack,
            "bond_agency_ratings": agency,
            "rating_scale": scale,
            "issuer_concentration": concentration,
        },
        # HTTP RatesCreditResult 同形
        "net_asset": nav,
        "total_bond_market_value": book["total_bond_market_value"],
        "bond_exposure_pct_nav": book["bond_exposure_pct_nav"],
        "weighted_duration_years": sensitivity["weighted_duration_years"],
        "portfolio_dv01": sensitivity["portfolio_dv01"],
        "portfolio_cs01": sensitivity["portfolio_cs01"],
        "krd_buckets": krd["rows"],
        "issuer_concentration": {
            "hhi": concentration["hhi"],
            "top_issuers": concentration["top_issuers"],
        },
        "rating_distribution": ratings_pack["rating_distribution"],
        "investment_grade_pct": ratings_pack["investment_grade_pct"],
        "below_investment_grade_pct": ratings_pack["below_investment_grade_pct"],
        "issuer_rating_distribution": ratings_pack["issuer_rating_distribution"],
        "debt_rating_distribution": ratings_pack["debt_rating_distribution"],
        "issuer_investment_grade_pct": ratings_pack["issuer_investment_grade_pct"],
        "issuer_below_investment_grade_pct": ratings_pack["issuer_below_investment_grade_pct"],
        "debt_investment_grade_pct": ratings_pack["debt_investment_grade_pct"],
        "debt_below_investment_grade_pct": ratings_pack["debt_below_investment_grade_pct"],
        "bond_count": book["bond_count"],
        "rating_source": ratings_pack["rating_source"],
        "rating_source_options": ratings_pack["rating_source_options"],
        "rating_matched_bond_count": ratings_pack["rating_matched_bond_count"],
        "rating_matched_market_value": ratings_pack["rating_matched_market_value"],
        "rating_agency_counts": ratings_pack["rating_agency_counts"],
        "bond_agency_rating_columns": agency["bond_agency_rating_columns"],
        "bond_agency_rating_rows": agency["rows"],
        "rating_scale_legend": scale["rating_scale_legend"],
        "rating_scale_note": scale["rating_scale_note"],
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    book = modules.get("bond_book") or {}
    if book.get("bond_count", 0) > 0 and book.get("total_bond_market_value") is None:
        errors.append("bond_book.total_bond_market_value")
    sens = modules.get("sensitivity") or {}
    for key in ("weighted_duration_years", "portfolio_dv01", "portfolio_cs01"):
        if key not in sens:
            errors.append(f"sensitivity.{key}")
    krd = modules.get("krd_buckets") or {}
    buckets = {row.get("bucket") for row in (krd.get("rows") or [])}
    for name in R.MATURITY_BUCKETS:
        if name not in buckets:
            errors.append(f"krd_buckets.{name}")
    rating = modules.get("rating_distribution") or {}
    for key in ("issuer_rating_distribution", "debt_rating_distribution", "issuer_investment_grade_pct"):
        if key not in rating:
            errors.append(f"rating_distribution.{key}")
    agency = modules.get("bond_agency_ratings") or {}
    if "rows" not in agency:
        errors.append("bond_agency_ratings.rows")
    scale = modules.get("rating_scale") or {}
    if not scale.get("rating_scale_legend"):
        errors.append("rating_scale.legend")
    conc = modules.get("issuer_concentration") or {}
    if "top_issuers" not in conc or "hhi" not in conc:
        errors.append("issuer_concentration")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
