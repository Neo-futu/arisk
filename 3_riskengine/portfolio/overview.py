"""投资风险 · 组合概况业务模块（``/investment-risk/overview``）。

资管风控口径（非 UI 控件）：

1. **组合** — 身份、币种、产品线、AUM、单位净值、日收益
2. **区间收益** — 1日 / 1月 / 3月 / 年初至今 / 1年 / 成立以来
3. **资产配置结构** — LOOK_THROUGH 资产类别市值与权重
4. **前十大个股** — EQUITY 市值 Top 10
5. **前十大个券** — BOND/CD 市值 Top 10（含 YTM/久期/票息）
6. **股票行业配置** — 个股按 sector 汇总

权威持仓/NAV 仍来自 ``fsi.balance_*``；本模块在 ``RiskEngine.bind(snapshot)``
上给出可对账、可单测的同一业务数字。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from ..core.contracts import ProductKind, ViewMode
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..instruments.classify import issuer_name
from .aggregate import aggregate

BUSINESS_MODULES = (
    "portfolio",
    "performance",
    "asset_allocation",
    "top_stocks",
    "top_bonds",
    "stock_sectors",
)

# 页面 ASSET_LABELS 使用的平台资产类代码（引擎 ProductKind → 展示类）
_KIND_TO_PLATFORM: dict[str, str] = {
    ProductKind.CASH.value: "CASH",
    ProductKind.DEPOSIT.value: "DEPOSIT",
    ProductKind.CD.value: "CD",
    ProductKind.BOND.value: "BOND_CORP",
    ProductKind.REPO.value: "REPO",
    ProductKind.EQUITY.value: "STOCK",
    ProductKind.ETF.value: "FUND_ETF",
    ProductKind.FUND.value: "FUND_PUBLIC",
    ProductKind.MMF.value: "FUND_PUBLIC",
    ProductKind.FUTURE.value: "FUTURES",
    ProductKind.OPTION.value: "OPTIONS",
    ProductKind.FX.value: "OTHER",
    ProductKind.FX_FORWARD.value: "OTHER",
    ProductKind.FX_OPTION.value: "OPTIONS",
    ProductKind.IRS.value: "OTHER",
    ProductKind.SWAP.value: "OTHER",
    ProductKind.SWAPTION.value: "OPTIONS",
    ProductKind.CDS.value: "OTHER",
    ProductKind.STRUCTURED.value: "OTHER",
}

EQUITY_KINDS = frozenset({ProductKind.EQUITY.value, ProductKind.ETF.value})
BOND_KINDS = frozenset({ProductKind.BOND.value, ProductKind.CD.value})


def _nav(snapshot: Any) -> float:
    return float(getattr(snapshot, "net_asset", 0.0) or 0.0)


def _meta(product: Any) -> dict[str, Any]:
    return dict(getattr(product, "metadata", None) or {})


def _platform_class(kind: str) -> str:
    return _KIND_TO_PLATFORM.get(str(kind).upper(), str(kind).upper() or "OTHER")


def nav_points_from_snapshot(snapshot: Any, history: Sequence[Mapping[str, Any]] | None = None) -> list[tuple[date, float]]:
    """(date, nav_level) 序列：优先外部 history，否则由 nav_returns 复利。"""

    if history:
        points: list[tuple[date, float]] = []
        for row in history:
            raw = row.get("evaluate_date") or row.get("date")
            nav = row.get("nav") or row.get("unit_nav") or row.get("acc_unit_nav")
            if raw is None or nav is None:
                continue
            when = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
            points.append((when, float(nav)))
        return points

    returns = list(getattr(snapshot, "nav_returns", None) or ())
    if not returns:
        return []
    level = 1.0
    points = []
    for when, ret in returns:
        level *= 1.0 + float(ret)
        day = when if isinstance(when, date) else date.fromisoformat(str(when)[:10])
        points.append((day, level))
    return points


def performance_periods(points: Sequence[tuple[date, float]]) -> list[dict[str, Any]]:
    """区间收益表：与 processing ``_performance_periods`` 同一套窗口。"""

    if len(points) < 2:
        return []
    end_date, end_nav = points[-1]
    targets: list[tuple[str, date | None]] = [
        ("1日", None),
        ("1月", end_date - timedelta(days=30)),
        ("3月", end_date - timedelta(days=90)),
        ("年初至今", date(end_date.year, 1, 1) - timedelta(days=1)),
        ("1年", end_date - timedelta(days=365)),
        ("成立以来", points[0][0]),
    ]
    periods: list[dict[str, Any]] = []
    for label, target in targets:
        if label == "1日":
            start_date, start_nav = points[-2]
        elif label == "成立以来":
            start_date, start_nav = points[0]
        else:
            candidates = [point for point in points if point[0] <= target]  # type: ignore[operator]
            if not candidates:
                continue
            start_date, start_nav = candidates[-1]
        if not start_nav:
            continue
        periods.append(
            {
                "period": label,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "return_pct": (end_nav / start_nav - 1.0) * 100.0,
            }
        )
    return periods


def cumulative_return_series(points: Sequence[tuple[date, float]]) -> list[dict[str, Any]]:
    """累计收益曲线（首日=0%），供概况页收益趋势图。"""

    if not points:
        return []
    base = points[0][1]
    if not base:
        return []
    return [
        {
            "date": when.isoformat(),
            "nav": level,
            "cumulative_return_pct": (level / base - 1.0) * 100.0,
        }
        for when, level in points
    ]


def module_portfolio(bound: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    snapshot = bound.snapshot
    info = dict(meta or {})
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    returns = list(getattr(snapshot, "nav_returns", None) or ())
    day = info.get("day_return")
    if day is None and returns:
        day = float(returns[-1][1])
    return {
        "module": "portfolio",
        "fund_id": str(info.get("fund_id") or snapshot.fund_id),
        "port_name": str(info.get("port_name") or snapshot.fund_id),
        "portfolio_type": str(info.get("portfolio_type") or info.get("port_type") or quality.get("port_type") or "MIXED"),
        "base_currency": str(snapshot.reporting_currency),
        "data_date": snapshot.as_of_date.isoformat(),
        "net_asset": _nav(snapshot),
        "unit_nav": float(info["unit_nav"]) if info.get("unit_nav") is not None else None,
        "acc_unit_nav": float(info["acc_unit_nav"]) if info.get("acc_unit_nav") is not None else None,
        "day_return": None if day is None else float(day),
        "shares_outstanding": info.get("shares_outstanding"),
        "position_count": len(getattr(snapshot, "positions", ()) or ()),
    }


def module_performance(
    bound: Any,
    *,
    history: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    points = nav_points_from_snapshot(bound.snapshot, history)
    periods = performance_periods(points)
    series = cumulative_return_series(points)
    return {
        "module": "performance",
        "periods": periods,
        "timeseries": series,
        "observations": len(points),
        "formula": "return_pct = (nav_end / nav_start - 1) × 100",
    }


def module_asset_allocation(bound: Any) -> dict[str, Any]:
    book = aggregate(bound, view=ViewMode.LOOK_THROUGH)
    nav = float(book["nav"] or 0.0) or 1.0
    buckets: dict[str, float] = defaultdict(float)
    for row in book.get("positions") or []:
        klass = _platform_class(str(row.get("asset_class") or "OTHER"))
        buckets[klass] += float(row.get("base_pv") or 0.0)
    allocation = [
        {
            "asset_class": klass,
            "market_value_base": value,
            "weight_pct": value / nav * 100.0,
        }
        for klass, value in sorted(buckets.items(), key=lambda item: abs(item[1]), reverse=True)
    ]
    return {
        "module": "asset_allocation",
        "view": "LOOK_THROUGH",
        "nav": float(book["nav"] or 0.0),
        "rows": allocation,
        "chart": {
            "id": "allocation",
            "kind": "hbar",
            "points": [{"label": row["asset_class"], "value": row["weight_pct"]} for row in allocation],
        },
    }


def _holding_rows(bound: Any, kinds: frozenset[str]) -> list[dict[str, Any]]:
    products = bound.products(view="LOOK_THROUGH")
    nav = _nav(bound.snapshot) or 1.0
    rows: list[dict[str, Any]] = []
    for product in products:
        kind = str(getattr(product.kind, "value", product.kind))
        if kind not in kinds:
            continue
        meta = _meta(product)
        instrument = product.instrument
        mv = float(getattr(product, "market_value_base", 0.0) or 0.0)
        rows.append(
            {
                "security_code": instrument.instrument_id,
                "security_name": instrument.name or instrument.instrument_id,
                "asset_class": kind,
                "sector": str(meta.get("sector") or meta.get("industry") or "未分类"),
                "issuer_name": issuer_name(product),
                "rating": meta.get("rating") or meta.get("debt_rating") or meta.get("issuer_rating"),
                "currency": str(product.currency),
                "market_value_base": mv,
                "weight_pct": mv / nav * 100.0,
                "unrealized_pnl": float(meta["unrealized_pnl"]) if meta.get("unrealized_pnl") is not None else 0.0,
                "ytm": float(getattr(product, "ytm", 0.0) or meta.get("ytm") or 0.0) or None,
                "duration": float(getattr(product, "duration", 0.0) or meta.get("duration") or 0.0) or None,
                "coupon_rate": float(getattr(product, "coupon_rate", 0.0) or meta.get("coupon_rate") or 0.0) or None,
                "maturity_date": (
                    product.maturity_date.isoformat()
                    if getattr(product, "maturity_date", None) is not None
                    else None
                ),
            }
        )
    rows.sort(key=lambda item: abs(item["market_value_base"]), reverse=True)
    return rows


def module_top_stocks(bound: Any, *, limit: int = 10) -> dict[str, Any]:
    rows = _holding_rows(bound, EQUITY_KINDS)[: max(int(limit), 1)]
    return {
        "module": "top_stocks",
        "limit": int(limit),
        "rows": rows,
        "count": len(rows),
    }


def module_top_bonds(bound: Any, *, limit: int = 10) -> dict[str, Any]:
    rows = _holding_rows(bound, BOND_KINDS)[: max(int(limit), 1)]
    return {
        "module": "top_bonds",
        "limit": int(limit),
        "rows": rows,
        "count": len(rows),
    }


def module_stock_sectors(bound: Any) -> dict[str, Any]:
    stocks = _holding_rows(bound, EQUITY_KINDS)
    buckets: dict[str, dict[str, float]] = defaultdict(
        lambda: {"market_value_base": 0.0, "weight_pct": 0.0, "position_count": 0.0}
    )
    for row in stocks:
        sector = str(row.get("sector") or "未分类")
        bucket = buckets[sector]
        bucket["market_value_base"] += float(row["market_value_base"])
        bucket["weight_pct"] += float(row["weight_pct"])
        bucket["position_count"] += 1.0
    sectors = [
        {
            "sector": name,
            "market_value_base": values["market_value_base"],
            "weight_pct": values["weight_pct"],
            "position_count": int(values["position_count"]),
        }
        for name, values in sorted(buckets.items(), key=lambda item: abs(item[1]["market_value_base"]), reverse=True)
    ]
    return {
        "module": "stock_sectors",
        "rows": sectors,
        "count": len(sectors),
        "source": "position.metadata.sector|industry（平台可对齐 v_mktdata_stock_industry_current）",
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    history: Sequence[Mapping[str, Any]] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """组合概况六大业务模块打包。"""

    portfolio = module_portfolio(bound, meta=meta)
    performance = module_performance(bound, history=history)
    allocation = module_asset_allocation(bound)
    stocks = module_top_stocks(bound, limit=top_n)
    bonds = module_top_bonds(bound, limit=top_n)
    sectors = module_stock_sectors(bound)
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/overview",
        "fund_id": portfolio["fund_id"],
        "as_of_date": portfolio["data_date"],
        "business_modules": list(BUSINESS_MODULES),
        "modules": {
            "portfolio": portfolio,
            "performance": performance,
            "asset_allocation": allocation,
            "top_stocks": stocks,
            "top_bonds": bonds,
            "stock_sectors": sectors,
        },
        # HTTP overview 同形，便于对账 / 单测
        "portfolio": portfolio,
        "performance": performance["periods"],
        "asset_allocation": allocation["rows"],
        "top_stocks": stocks["rows"],
        "top_bonds": bonds["rows"],
        "stock_sectors": sectors["rows"],
        "timeseries": performance["timeseries"],
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    portfolio = modules.get("portfolio") or {}
    if not portfolio.get("fund_id"):
        errors.append("portfolio.fund_id")
    if portfolio.get("net_asset") is None:
        errors.append("portfolio.net_asset")
    if not (modules.get("asset_allocation") or {}).get("rows"):
        errors.append("asset_allocation.rows")
    perf = modules.get("performance") or {}
    if perf.get("observations", 0) >= 2 and not perf.get("periods"):
        errors.append("performance.periods")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
