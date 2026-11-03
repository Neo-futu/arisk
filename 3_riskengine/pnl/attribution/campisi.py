"""Campisi 债券归因：收入、国债、利差、择券。

RiskEngine 独立模型实现（``3_riskengine.pnl.attribution``），不依赖 2_processing。

对齐 DolphinDB Campisi 教程：
无基准、不考虑凸性：
  国债效应 = -久期 * 国债收益率变化
  利差效应 = 总收益 - 收入效应 - 国债效应
有基准、不考虑凸性：
  国债效应 = -久期 * 国债收益率变化
  利差效应 = -久期 * 利差变化
  择券效应 = 总收益 - 收入效应 - 国债效应 - 利差效应
考虑凸性时国债/利差额外加上 0.5 * (变化)^2 * 凸性。

多期链接（区间效应）：
  r = Σ_t  r_t * Π_{s>t}(1+R_s)
其中 R_s 为第 s 期组合总收益。该式对总收益本身满足
  Σ R_t * Π_{s>t}(1+R_s) = Π(1+R) - 1。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


def interpolate_yield(curve: list[tuple[float, float]], tenor_years: float) -> float | None:
    """线性插值。curve 为 (期限年, 收益率小数)，已排序与否均可。"""
    points = sorted((float(tenor), float(value)) for tenor, value in curve if tenor is not None)
    if not points:
        return None
    if tenor_years <= points[0][0]:
        return points[0][1]
    if tenor_years >= points[-1][0]:
        return points[-1][1]
    for (left_t, left_y), (right_t, right_y) in zip(points, points[1:]):
        if left_t <= tenor_years <= right_t and right_t > left_t:
            weight = (tenor_years - left_t) / (right_t - left_t)
            return left_y + weight * (right_y - left_y)
    return points[-1][1]


def campisi(
    positions: list[dict[str, Any]],
    *,
    benchmark: bool = False,
    convexity: bool = False,
    multi_period: bool = False,
    group_by: str = "industry",
) -> dict[str, Any]:
    """计算 Campisi。

    positions 每行（一期一券）：
    date, symbol, weight, asset, industry,
    total_return, income, duration, treasury_change,
    spread_change（有基准时）, convexity（可选）
    收益率与权重均为小数。
    """
    if group_by not in {"asset", "industry", "symbol", "portfolio"}:
        raise ValueError(f"unsupported group_by: {group_by}")
    by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in positions:
        day = row.get("date")
        if isinstance(day, date):
            by_date[day].append(row)
    dates = sorted(by_date)
    if not dates:
        return _empty(benchmark, convexity, group_by)

    periods = [
        _single(by_date[day], benchmark=benchmark, convexity=convexity, group_by=group_by, day=day)
        for day in dates
    ]
    use_multi = multi_period and len(periods) > 1
    linked = _link(periods) if use_multi else periods[0]
    return {
        "benchmark": benchmark,
        "convexity": convexity,
        "multi_period": use_multi,
        "group_by": group_by,
        "total_return": linked["total_return"],
        "income": linked["income"],
        "treasury": linked["treasury"],
        "spread": linked["spread"],
        "selection": linked["selection"],
        "groups": linked["groups"],
        "periods": periods if use_multi else periods[:1],
    }


def _empty(benchmark: bool, convexity: bool, group_by: str) -> dict[str, Any]:
    return {
        "benchmark": benchmark,
        "convexity": convexity,
        "multi_period": False,
        "group_by": group_by,
        "total_return": 0.0,
        "income": 0.0,
        "treasury": 0.0,
        "spread": 0.0,
        "selection": 0.0,
        "groups": [],
        "periods": [],
    }


def _label(row: dict[str, Any], group_by: str) -> str:
    if group_by == "portfolio":
        return "PORTFOLIO"
    if group_by == "symbol":
        return str(row.get("symbol") or "UNKNOWN")
    if group_by == "asset":
        return str(row.get("asset") or "BOND")
    return str(row.get("industry") or "未分类")


def _effects(row: dict[str, Any], *, benchmark: bool, convexity: bool) -> dict[str, float]:
    total = float(row.get("total_return") or 0.0)
    income = float(row.get("income") or 0.0)
    duration = float(row.get("duration") or 0.0)
    dy = float(row.get("treasury_change") or 0.0)
    conv = float(row.get("convexity") or 0.0)
    treasury = -duration * dy
    if convexity:
        treasury += 0.5 * dy * dy * conv
    if benchmark:
        spread_change = float(row.get("spread_change") or 0.0)
        spread = -duration * spread_change
        if convexity:
            spread += 0.5 * spread_change * spread_change * conv
        selection = total - income - treasury - spread
    else:
        spread = total - income - treasury
        selection = 0.0
    return {
        "total_return": total,
        "income": income,
        "treasury": treasury,
        "spread": spread,
        "selection": selection,
    }


def _single(
    rows: list[dict[str, Any]],
    *,
    benchmark: bool,
    convexity: bool,
    group_by: str,
    day: date,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, float]] = {}
    total_weight = sum(float(row.get("weight") or 0.0) for row in rows) or 1.0
    portfolio_total = portfolio_income = portfolio_treasury = portfolio_spread = portfolio_selection = 0.0
    for row in rows:
        weight = float(row.get("weight") or 0.0)
        share = weight / total_weight if total_weight else 0.0
        effects = _effects(row, benchmark=benchmark, convexity=convexity)
        label = _label(row, group_by)
        bucket = grouped.setdefault(
            label,
            {
                "group": label,
                "weight": 0.0,
                "total_return": 0.0,
                "income": 0.0,
                "treasury": 0.0,
                "spread": 0.0,
                "selection": 0.0,
            },
        )
        bucket["weight"] += share
        for key in ("total_return", "income", "treasury", "spread", "selection"):
            bucket[key] += share * effects[key]
        portfolio_total += share * effects["total_return"]
        portfolio_income += share * effects["income"]
        portfolio_treasury += share * effects["treasury"]
        portfolio_spread += share * effects["spread"]
        portfolio_selection += share * effects["selection"]
    groups = sorted(grouped.values(), key=lambda item: abs(item["total_return"]), reverse=True)
    return {
        "date": day.isoformat(),
        "total_return": portfolio_total,
        "income": portfolio_income,
        "treasury": portfolio_treasury,
        "spread": portfolio_spread,
        "selection": portfolio_selection,
        "groups": groups,
    }


def _link(periods: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [p["total_return"] for p in periods]

    def linked(key: str) -> float:
        value = 0.0
        for index, period in enumerate(periods):
            factor = 1.0
            for later in totals[index + 1 :]:
                factor *= 1.0 + later
            value += period[key] * factor
        return value

    labels = {row["group"] for period in periods for row in period["groups"]}
    groups = []
    for label in labels:
        series = []
        for period in periods:
            match = next((row for row in period["groups"] if row["group"] == label), None)
            series.append(match)
        def linked_group(key: str) -> float:
            value = 0.0
            for index, row in enumerate(series):
                factor = 1.0
                for later in totals[index + 1 :]:
                    factor *= 1.0 + later
                if row:
                    value += row[key] * factor
            return value

        groups.append(
            {
                "group": label,
                "weight": sum((row["weight"] if row else 0.0) for row in series) / len(series),
                "total_return": linked_group("total_return"),
                "income": linked_group("income"),
                "treasury": linked_group("treasury"),
                "spread": linked_group("spread"),
                "selection": linked_group("selection"),
            }
        )
    groups.sort(key=lambda item: abs(item["total_return"]), reverse=True)
    return {
        "total_return": linked("total_return"),
        "income": linked("income"),
        "treasury": linked("treasury"),
        "spread": linked("spread"),
        "selection": linked("selection"),
        "groups": groups,
    }
