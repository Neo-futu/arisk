"""组合驾驶舱业务模块 — 资管风控引擎口径。

对应前端 ``/portfolio-cockpit`` 展示的**业务能力**（不是 UI 控件）：

1. **组合** — 组合身份、币种、产品线类型、估值日
2. **组合规模** — AUM / NAV、账面 PV、Gross/Net、杠杆
3. **持仓资产类型** — LOOK_THROUGH 按 ProductKind / asset_class 的市值与权重
4. **收益** — 日收益、区间收益、七日年化（货基）、NAV 收益序列
5. **净值** — 单位/累计净值、历史曲线、指数化净值

列表主数据权威仍是 ``fsi.para_portfolio`` + ``fsi.balance_portfolio_nav``；
RiskEngine 在 ``bind(snapshot)`` 后给出可对账、可下钻的同一套业务数字。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from ..core.contracts import ViewMode
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..limits.sfc import compliance_status
from .aggregate import aggregate

BUSINESS_MODULES = (
    "portfolio",
    "scale",
    "holdings_asset_mix",
    "returns",
    "nav",
)

# 列表行仍与 HTTP overview 对齐（供多组合总览）
ROW_KEYS = (
    "port_id",
    "port_name",
    "port_type",
    "base_currency",
    "is_mmf",
    "as_of_date",
    "net_asset",
    "unit_nav",
    "acc_unit_nav",
    "day_return",
    "return_rate_7d",
    "period_return",
    "wam_days",
    "wal_days",
    "wam_limit_days",
    "wal_limit_days",
    "nav_deviation",
    "income_per_10k",
    "status",
    "has_data",
    "sparkline",
    "history",
)

SUMMARY_KEYS = (
    "total_portfolios",
    "with_data",
    "mmf_count",
    "breached",
    "warned",
    "by_type",
    "total_aum",
)

TABLE_COLUMNS = (
    "port_name",
    "port_type",
    "base_currency",
    "as_of_date",
    "net_asset",
    "unit_nav",
    "acc_unit_nav",
    "day_return",
    "period_return",
    "return_rate_7d",
)

# 业务图：规模 / 持仓资产类型 / 收益 / 净值（区别于仅产品线类型饼图）
CHART_IDS = ("aum", "holdings_mix", "return", "nav")
# 兼容旧 UI 产品线类型饼
LEGACY_CHART_IDS = ("aum", "mix", "return", "nav")


def period_return(history: Sequence[Mapping[str, Any]]) -> float | None:
    """区间收益 = 期末单位净值 / 期初单位净值 − 1。"""

    navs = [float(point["unit_nav"]) for point in history if point.get("unit_nav")]
    if len(navs) < 2 or not navs[0]:
        return None
    return navs[-1] / navs[0] - 1.0


def indexed_nav_series(history: Sequence[Mapping[str, Any]], *, base: float = 100.0) -> list[dict[str, Any]]:
    """净值指数化：首日 unit_nav 映射为 ``base``（常用 100）。"""

    points = [
        {"date": point.get("date"), "unit_nav": float(point["unit_nav"])}
        for point in history
        if point.get("date") and point.get("unit_nav") is not None and float(point["unit_nav"]) > 0
    ]
    if not points:
        return []
    first = points[0]["unit_nav"]
    return [
        {"date": item["date"], "indexed": (item["unit_nav"] / first) * base, "unit_nav": item["unit_nav"]}
        for item in points
    ]


def sparkline_from_history(history: Sequence[Mapping[str, Any]]) -> list[float]:
    return [float(point["net_asset"]) for point in history if point.get("net_asset") is not None]


def yield_7d_annualized(nav_returns: Sequence[float]) -> float | None:
    """近 7 个交易日收益复利年化（×365/7）。样本不足返回 None。"""

    series = [float(x) for x in nav_returns[-7:]]
    if len(series) < 7:
        return None
    wealth = 1.0
    for ret in series:
        wealth *= 1.0 + ret
    return (wealth ** (365.0 / 7.0) - 1.0) * 100.0


def _history_from_snapshot(snapshot: Any, info: Mapping[str, Any]) -> list[dict[str, Any]]:
    hist = [dict(item) for item in (info.get("history") or ())]
    if hist:
        return hist
    returns = list(getattr(snapshot, "nav_returns", None) or ())
    if not returns:
        return []
    level = 1.0
    nav = float(getattr(snapshot, "net_asset", 0.0) or 0.0)
    out: list[dict[str, Any]] = []
    for when, ret in returns:
        level *= 1.0 + float(ret)
        out.append(
            {
                "date": when.isoformat() if hasattr(when, "isoformat") else str(when),
                "unit_nav": level,
                "net_asset": nav * level / (level if level else 1.0),
                "day_return": float(ret),
            }
        )
    # 末端对齐到当前 AUM（指数轨迹保留）
    if out and nav:
        scale = nav / float(out[-1]["net_asset"] or nav)
        for item in out:
            item["net_asset"] = float(item["net_asset"]) * scale
    return out


def module_portfolio(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """业务模块 1：组合身份。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    engine_mmf = bound.liquidity().mmf()
    is_mmf = bool(info.get("is_mmf", engine_mmf.get("is_mmf") or quality.get("is_mmf")))
    return {
        "module": "portfolio",
        "port_id": str(info.get("port_id") or snapshot.fund_id),
        "port_name": str(info.get("port_name") or snapshot.fund_id),
        "port_type": str(
            info.get("port_type") or quality.get("port_type") or ("MMF" if is_mmf else "MIXED")
        ),
        "base_currency": str(snapshot.reporting_currency),
        "as_of_date": snapshot.as_of_date.isoformat(),
        "is_mmf": is_mmf,
        "position_count": len(getattr(snapshot, "positions", ()) or ()),
        "source_tables": ["fsi.para_portfolio", "fsi.balance_*"],
    }


def module_scale(bound: Any) -> dict[str, Any]:
    """业务模块 2：组合规模（AUM / 敞口）。"""

    book = aggregate(bound, view=ViewMode.LOOK_THROUGH)
    nav = float(book["nav"] or 0.0)
    return {
        "module": "scale",
        "reporting_currency": book["reporting_currency"],
        "as_of": book["as_of"],
        "aum": nav,
        "net_asset": nav,
        "base_pv": float(book["base_pv"]),
        "gross_exposure": float(book["gross"]),
        "net_exposure": float(book["net"]),
        "leverage": book["leverage"],
        "pv_vs_nav": float(book["base_pv"]) - nav,
        "position_count": int(book["position_count"]),
        "formula": {
            "aum": "fsi.balance_portfolio_nav.net_asset",
            "gross": "sum(|position PV|)",
            "net": "sum(position PV)",
            "leverage": "gross / AUM",
        },
    }


def module_holdings_asset_mix(bound: Any) -> dict[str, Any]:
    """业务模块 3：持仓资产类型（穿透后 ProductKind 权重）。"""

    book = aggregate(bound, view=ViewMode.LOOK_THROUGH)
    mix = []
    for klass, bucket in (book.get("by_asset_class") or {}).items():
        mix.append(
            {
                "asset_class": klass,
                "market_value": float(bucket["base_pv"]),
                "weight": float(bucket["weight"]),
                "weight_pct": float(bucket["weight"]) * 100.0,
            }
        )
    mix.sort(key=lambda item: abs(item["market_value"]), reverse=True)
    return {
        "module": "holdings_asset_mix",
        "view": "LOOK_THROUGH",
        "nav": float(book["nav"] or 0.0),
        "classes": mix,
        "chart": {
            "id": "holdings_mix",
            "kind": "pie",
            "points": [
                {
                    "id": item["asset_class"],
                    "label": item["asset_class"],
                    "value": item["market_value"],
                    "weight_pct": item["weight_pct"],
                }
                for item in mix
            ],
        },
        "note": "持仓资产类型 ≠ 产品线类型(port_type)。本模块按 LOOK_THROUGH 持仓归类。",
    }


def module_returns(
    bound: Any,
    *,
    history: Sequence[Mapping[str, Any]] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """业务模块 4：收益。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    hist = list(history) if history is not None else _history_from_snapshot(snapshot, info)
    nav_rets = [float(item[1]) for item in (getattr(snapshot, "nav_returns", None) or ())]
    day = info.get("day_return")
    if day is None and hist and hist[-1].get("day_return") is not None:
        day = hist[-1]["day_return"]
    if day is None and nav_rets:
        day = nav_rets[-1]
    y7 = info.get("return_rate_7d")
    if y7 is None:
        y7 = yield_7d_annualized(nav_rets)
    period = period_return(hist)
    fund = bound.portfolio().fund_risk()
    return {
        "module": "returns",
        "day_return": None if day is None else float(day),
        "day_return_pct": None if day is None else float(day) * 100.0,
        "period_return": period,
        "period_return_pct": None if period is None else float(period) * 100.0,
        "return_rate_7d": None if y7 is None else float(y7),
        "observations": len(nav_rets),
        "volatility_ann": fund.get("volatility_ann"),
        "max_drawdown": fund.get("max_drawdown"),
        "var_cvar": fund.get("var_cvar"),
        "formula": {
            "period_return": "unit_nav_end / unit_nav_start - 1",
            "yield_7d": "(Π(1+r_i))^(365/7) - 1，百分数",
            "day_return": "fsi.balance_portfolio_nav.day_return 或 NAV 收益末日",
        },
    }


def module_nav(
    bound: Any,
    *,
    history: Sequence[Mapping[str, Any]] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """业务模块 5：净值。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    hist = list(history) if history is not None else _history_from_snapshot(snapshot, info)
    unit = info.get("unit_nav")
    if unit is None and hist:
        unit = hist[-1].get("unit_nav")
    if unit is None:
        unit = 1.0
    acc = info.get("acc_unit_nav")
    indexed = indexed_nav_series(hist)
    return {
        "module": "nav",
        "unit_nav": float(unit) if unit is not None else None,
        "acc_unit_nav": None if acc is None else float(acc),
        "as_of_date": snapshot.as_of_date.isoformat(),
        "history_points": len(hist),
        "history": hist,
        "sparkline_aum": sparkline_from_history(hist),
        "indexed": indexed,
        "chart": {
            "id": "nav",
            "kind": "line",
            "points": [{"x": item["date"], "y": item["indexed"]} for item in indexed],
        },
        "source": "fsi.balance_portfolio_nav（或 snapshot.nav_returns 合成）",
    }


def fundamentals(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """驾驶舱五大业务模块打包（资管风控引擎主入口）。"""

    info = dict(meta or {})
    hist = _history_from_snapshot(bound.snapshot, info)
    portfolio = module_portfolio(bound, meta=info)
    scale = module_scale(bound)
    holdings = module_holdings_asset_mix(bound)
    returns = module_returns(bound, history=hist, meta=info)
    nav = module_nav(bound, history=hist, meta=info)
    engine_mmf = bound.liquidity().mmf() if portfolio["is_mmf"] else None
    status = compliance_status(
        portfolio["is_mmf"],
        None if engine_mmf is None else engine_mmf.get("wam_days"),
        None if engine_mmf is None else engine_mmf.get("wal_days"),
        None if engine_mmf is None else engine_mmf.get("wam_limit"),
        None if engine_mmf is None else engine_mmf.get("wal_limit"),
        None if engine_mmf is None else engine_mmf.get("shadow_deviation_bp"),
    )
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/portfolio-cockpit",
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "portfolio": portfolio,
            "scale": scale,
            "holdings_asset_mix": holdings,
            "returns": returns,
            "nav": nav,
        },
        "charts": {
            "aum": {
                "id": "aum",
                "kind": "bar",
                "points": [
                    {
                        "id": portfolio["port_id"],
                        "label": portfolio["port_name"],
                        "value": scale["aum"],
                        "group": portfolio["base_currency"],
                    }
                ],
            },
            "holdings_mix": holdings["chart"],
            "return": {
                "id": "return",
                "kind": "bar",
                "points": [
                    {
                        "id": portfolio["port_id"],
                        "label": portfolio["port_name"],
                        "value": (
                            returns["period_return_pct"]
                            if returns["period_return_pct"] is not None
                            else returns["day_return_pct"]
                        )
                        or 0.0,
                    }
                ],
            },
            "nav": nav["chart"],
        },
        "sfc_status": status,
        "mmf": engine_mmf,
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    """校验五大业务模块齐全且关键数字可解释。"""

    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing module {name}")
            continue
        block = modules[name]
        if name == "portfolio" and not block.get("port_id"):
            errors.append("portfolio.port_id")
        if name == "scale" and block.get("aum") is None:
            errors.append("scale.aum")
        if name == "holdings_asset_mix" and not block.get("classes"):
            errors.append("holdings_asset_mix.classes")
        if name == "returns" and block.get("observations", 0) < 0:
            errors.append("returns.observations")
        if name == "nav" and block.get("unit_nav") is None:
            errors.append("nav.unit_nav")
    charts = pack.get("charts") or {}
    for chart_id in CHART_IDS:
        if chart_id not in charts:
            errors.append(f"charts.{chart_id}")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }


def build_row(
    *,
    port_id: str,
    port_name: str,
    port_type: str,
    base_currency: str,
    is_mmf: bool = False,
    as_of_date: date | str | None = None,
    net_asset: float | None = None,
    unit_nav: float | None = None,
    acc_unit_nav: float | None = None,
    day_return: float | None = None,
    return_rate_7d: float | None = None,
    history: Sequence[Mapping[str, Any]] | None = None,
    wam_days: float | None = None,
    wal_days: float | None = None,
    wam_limit_days: float | None = None,
    wal_limit_days: float | None = None,
    nav_deviation: float | None = None,
    income_per_10k: float | None = None,
    port_name_en: str | None = None,
    inception_date: str | None = None,
    sfc_code: str | None = None,
    mgmt_fee_bps: float | None = None,
) -> dict[str, Any]:
    """多组合列表行（HTTP overview 同形）。"""

    hist = [dict(item) for item in (history or ())]
    as_of = as_of_date.isoformat() if isinstance(as_of_date, date) else as_of_date
    status = compliance_status(
        bool(is_mmf),
        wam_days,
        wal_days,
        wam_limit_days,
        wal_limit_days,
        nav_deviation,
    )
    return {
        "port_id": str(port_id),
        "port_name": str(port_name),
        "port_name_en": port_name_en,
        "port_type": str(port_type),
        "base_currency": str(base_currency).strip(),
        "is_mmf": bool(is_mmf),
        "inception_date": inception_date,
        "sfc_code": sfc_code,
        "mgmt_fee_bps": mgmt_fee_bps,
        "as_of_date": as_of,
        "net_asset": None if net_asset is None else float(net_asset),
        "unit_nav": None if unit_nav is None else float(unit_nav),
        "acc_unit_nav": None if acc_unit_nav is None else float(acc_unit_nav),
        "day_return": None if day_return is None else float(day_return),
        "return_rate_7d": None if return_rate_7d is None else float(return_rate_7d),
        "period_return": period_return(hist),
        "wam_days": wam_days,
        "wal_days": wal_days,
        "wam_limit_days": wam_limit_days,
        "wal_limit_days": wal_limit_days,
        "nav_deviation": nav_deviation,
        "income_per_10k": income_per_10k,
        "status": status,
        "has_data": as_of is not None,
        "sparkline": sparkline_from_history(hist),
        "history": hist,
        "indexed_nav": indexed_nav_series(hist),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }


def build_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    portfolios = list(rows)
    by_type: dict[str, int] = {}
    total_aum: dict[str, float] = {}
    for row in portfolios:
        ptype = str(row.get("port_type") or "UNKNOWN")
        by_type[ptype] = by_type.get(ptype, 0) + 1
        nav = row.get("net_asset")
        if nav is not None:
            ccy = str(row.get("base_currency") or "UNK")
            total_aum[ccy] = total_aum.get(ccy, 0.0) + float(nav)
    return {
        "total_portfolios": len(portfolios),
        "with_data": sum(1 for row in portfolios if row.get("has_data")),
        "mmf_count": sum(1 for row in portfolios if row.get("is_mmf")),
        "breached": sum(1 for row in portfolios if row.get("status") == "breach"),
        "warned": sum(1 for row in portfolios if row.get("status") == "warn"),
        "by_type": by_type,
        "total_aum": total_aum,
    }


def charts_payload(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """多组合总览图：规模 / 产品线类型 / 收益 / 净值。

    注意：此处 ``mix`` 是 **产品线类型(port_type)** 跨组合分布；
    单组合 **持仓资产类型** 见 ``fundamentals(...).modules.holdings_asset_mix``。
    """

    aum = [
        {
            "id": row["port_id"],
            "label": row.get("port_name") or row["port_id"],
            "value": float(row["net_asset"]),
            "group": row.get("base_currency"),
        }
        for row in rows
        if row.get("net_asset") is not None
    ]
    by_type: dict[str, float] = {}
    for row in rows:
        ptype = str(row.get("port_type") or "UNKNOWN")
        by_type[ptype] = by_type.get(ptype, 0.0) + float(row.get("net_asset") or 0.0)
    returns = []
    for row in rows:
        value = row.get("period_return")
        if value is None:
            value = row.get("day_return")
        if value is None:
            continue
        returns.append(
            {
                "id": row["port_id"],
                "label": row.get("port_name") or row["port_id"],
                "value": float(value) * 100.0,
            }
        )
    nav_lines = []
    for row in rows:
        series = row.get("indexed_nav") or indexed_nav_series(row.get("history") or ())
        if not series:
            continue
        nav_lines.append(
            {
                "id": row["port_id"],
                "name": row.get("port_name") or row["port_id"],
                "points": [{"x": item["date"], "y": item["indexed"]} for item in series],
            }
        )
    return {
        "aum": {"id": "aum", "kind": "bar", "points": aum},
        "mix": {
            "id": "mix",
            "kind": "pie",
            "points": [{"id": k, "label": k, "value": v} for k, v in by_type.items()],
            "semantic": "port_type",
        },
        "return": {"id": "return", "kind": "bar", "points": returns},
        "nav": {"id": "nav", "kind": "line", "lines": nav_lines},
    }


def overview_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, Any]:
    def _iso(value: date | str | None) -> str | None:
        if value is None:
            return None
        return value.isoformat() if isinstance(value, date) else str(value)

    ended = _iso(end_date)
    return {
        "as_of_date": ended,
        "start_date": _iso(start_date),
        "end_date": ended,
        "summary": build_summary(rows),
        "portfolios": list(rows),
        "charts": charts_payload(rows),
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": {
            "path": "/portfolio-cockpit",
            "table_columns": list(TABLE_COLUMNS),
            "chart_ids": list(LEGACY_CHART_IDS),
            "business_modules": list(BUSINESS_MODULES),
        },
    }


def row_from_snapshot(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """快照 → 列表行 + 五大业务模块。"""

    pack = fundamentals(bound, meta=meta)
    modules = pack["modules"]
    portfolio = modules["portfolio"]
    scale = modules["scale"]
    returns = modules["returns"]
    nav = modules["nav"]
    mmf = pack.get("mmf") or {}
    hist = nav.get("history") or []
    row = build_row(
        port_id=portfolio["port_id"],
        port_name=portfolio["port_name"],
        port_type=portfolio["port_type"],
        base_currency=portfolio["base_currency"],
        is_mmf=portfolio["is_mmf"],
        as_of_date=portfolio["as_of_date"],
        net_asset=scale["aum"],
        unit_nav=nav.get("unit_nav"),
        acc_unit_nav=nav.get("acc_unit_nav"),
        day_return=returns.get("day_return"),
        return_rate_7d=returns.get("return_rate_7d"),
        history=hist,
        wam_days=mmf.get("wam_days"),
        wal_days=mmf.get("wal_days"),
        wam_limit_days=mmf.get("wam_limit"),
        wal_limit_days=mmf.get("wal_limit"),
        nav_deviation=mmf.get("shadow_deviation_bp"),
    )
    row["business"] = pack["modules"]
    row["charts"] = pack["charts"]
    row["engine_block"] = {
        "fundamentals": pack,
        "adapters": pack["adapters"],
    }
    return row


def verify_overview_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """多组合 overview 列表契约（兼容 HTTP）。"""

    errors: list[str] = []
    if "summary" not in payload:
        errors.append("missing summary")
    else:
        for key in SUMMARY_KEYS:
            if key not in payload["summary"]:
                errors.append(f"summary.{key}")
    portfolios = list(payload.get("portfolios") or [])
    for index, row in enumerate(portfolios):
        for key in ROW_KEYS:
            if key not in row:
                errors.append(f"portfolios[{index}].{key}")
        if row.get("status") not in {"ok", "warn", "breach"}:
            errors.append(f"portfolios[{index}].status_invalid")
    charts = payload.get("charts")
    if charts is not None:
        for chart_id in LEGACY_CHART_IDS:
            if chart_id not in charts:
                errors.append(f"charts.{chart_id}")
    return {
        "passed": not errors,
        "errors": errors,
        "portfolio_count": len(portfolios),
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }


def normalize_http_overview(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for raw in payload.get("portfolios") or []:
        row = dict(raw)
        hist = list(row.get("history") or ())
        if row.get("period_return") is None:
            row["period_return"] = period_return(hist)
        if not row.get("sparkline"):
            row["sparkline"] = sparkline_from_history(hist)
        row["indexed_nav"] = indexed_nav_series(hist)
        rows.append(row)
    overview = overview_from_rows(
        rows,
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date") or payload.get("as_of_date"),
    )
    if payload.get("summary"):
        overview["summary"] = dict(payload["summary"])
    overview["portfolios"] = rows
    return overview
