"""Brinson 归因（BHB / BF），单期与多期（GRAP 或直接相加）。

RiskEngine 独立模型实现（``3_riskengine.pnl.attribution``），不依赖 2_processing。

分组标签：asset（资产类型）、industry（行业）、symbol（单券）、portfolio（组合整体）。
可选在指定大类资产内再做行业归因。

公式对齐 DolphinDB Brinson 教程与 BHB(1986) / BF(1985)：
- BHB：配置 (w_p-w_b)*r_b；选择 w_b*(r_p-r_b)；交互 (w_p-w_b)*(r_p-r_b)
- BF：配置 (w_p-w_b)*(r_b-R_b)；选择 w_p*(r_p-r_b)（交互并入选择）
- 多期 GRAP：效应_t * Π_{i<t}(1+R_p,i) * Π_{i>t}(1+R_b,i)
  各期修正后相加等于 Π(1+R_p) - Π(1+R_b)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


def brinson(
    portfolio: list[dict[str, Any]],
    benchmark: list[dict[str, Any]],
    *,
    method: str = "BHB",
    multi_period: bool = False,
    multi_period_method: str = "grap",
    group_by: str = "asset",
    industry_within_assets: list[str] | None = None,
) -> dict[str, Any]:
    """计算 Brinson 归因。

    portfolio / benchmark 每行：
    date, symbol, weight, asset, industry, return_period
    weight 与 return_period 均为小数（0.01 = 1%）。同一 date 为一期，
    return_period 为该期区间收益，weight 为期初权重。
    """
    method_u = method.upper()
    if method_u not in {"BHB", "BF"}:
        raise ValueError(f"unsupported brinson method: {method}")
    link = multi_period_method.lower()
    if link not in {"grap", "sum"}:
        raise ValueError(f"unsupported multi_period_method: {multi_period_method}")
    if group_by not in {"asset", "industry", "symbol", "portfolio"}:
        raise ValueError(f"unsupported group_by: {group_by}")

    port_by_date = _by_date(portfolio)
    bench_by_date = _by_date(benchmark)
    dates = sorted(set(port_by_date) | set(bench_by_date))
    if not dates:
        return _empty(method_u, multi_period, link, group_by)

    period_results = [
        _single_period(
            port_by_date.get(day, []),
            bench_by_date.get(day, []),
            method_u,
            group_by,
            day,
        )
        for day in dates
    ]
    use_multi = multi_period and len(period_results) > 1
    linked = _link_periods(period_results, link if use_multi else "sum")
    industry_detail = None
    if industry_within_assets:
        industry_detail = {
            asset: brinson(
                [row for row in portfolio if str(row.get("asset") or "") == asset],
                [row for row in benchmark if str(row.get("asset") or "") == asset],
                method=method_u,
                multi_period=multi_period,
                multi_period_method=link,
                group_by="industry",
            )
            for asset in industry_within_assets
        }
    return {
        "method": method_u,
        "multi_period": use_multi,
        "multi_period_method": link if use_multi else "single",
        "group_by": group_by,
        "portfolio_return": linked["portfolio_return"],
        "benchmark_return": linked["benchmark_return"],
        "active_return": linked["active_return"],
        "allocation": linked["allocation"],
        "selection": linked["selection"],
        "interaction": linked["interaction"],
        "groups": linked["groups"],
        "periods": period_results if use_multi else period_results[:1],
        "industry_within": industry_detail,
    }


def _empty(method: str, multi_period: bool, link: str, group_by: str) -> dict[str, Any]:
    return {
        "method": method,
        "multi_period": multi_period,
        "multi_period_method": link,
        "group_by": group_by,
        "portfolio_return": 0.0,
        "benchmark_return": 0.0,
        "active_return": 0.0,
        "allocation": 0.0,
        "selection": 0.0,
        "interaction": 0.0,
        "groups": [],
        "periods": [],
        "industry_within": None,
    }


def _by_date(rows: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        day = row.get("date")
        if not isinstance(day, date):
            continue
        grouped[day].append(row)
    return grouped


def _label(row: dict[str, Any], group_by: str) -> str:
    if group_by == "portfolio":
        return "PORTFOLIO"
    if group_by == "symbol":
        return str(row.get("symbol") or "UNKNOWN")
    if group_by == "industry":
        return str(row.get("industry") or "未分类")
    return str(row.get("asset") or "OTHER")


def _aggregate(rows: list[dict[str, Any]], group_by: str) -> dict[str, tuple[float, float]]:
    weight: dict[str, float] = defaultdict(float)
    weighted_return: dict[str, float] = defaultdict(float)
    for row in rows:
        label = _label(row, group_by)
        w = float(row.get("weight") or 0.0)
        r = float(row.get("return_period") or 0.0)
        weight[label] += w
        weighted_return[label] += w * r
    return {
        label: (w, weighted_return[label] / w if w else 0.0)
        for label, w in weight.items()
    }


def _single_period(
    portfolio_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    method: str,
    group_by: str,
    day: date,
) -> dict[str, Any]:
    port = _aggregate(portfolio_rows, group_by)
    bench = _aggregate(benchmark_rows, group_by)
    port_return = sum(w * r for w, r in port.values())
    bench_return = sum(w * r for w, r in bench.values())
    groups = []
    allocation = selection = interaction = 0.0
    for label in sorted(set(port) | set(bench)):
        wp, rp = port.get(label, (0.0, 0.0))
        wb, rb = bench.get(label, (0.0, 0.0))
        if method == "BF":
            alloc = (wp - wb) * (rb - bench_return)
            sel = wp * (rp - rb)
            inter = 0.0
        else:
            alloc = (wp - wb) * rb
            sel = wb * (rp - rb)
            inter = (wp - wb) * (rp - rb)
        allocation += alloc
        selection += sel
        interaction += inter
        groups.append(
            {
                "group": label,
                "portfolio_weight": wp,
                "benchmark_weight": wb,
                "portfolio_return": rp,
                "benchmark_return": rb,
                "allocation": alloc,
                "selection": sel,
                "interaction": inter,
                "active": alloc + sel + inter,
            }
        )
    groups.sort(key=lambda row: abs(row["active"]), reverse=True)
    return {
        "date": day.isoformat(),
        "portfolio_return": port_return,
        "benchmark_return": bench_return,
        "active_return": port_return - bench_return,
        "allocation": allocation,
        "selection": selection,
        "interaction": interaction,
        "groups": groups,
    }


def _link_periods(periods: list[dict[str, Any]], method: str) -> dict[str, Any]:
    if len(periods) == 1:
        only = periods[0]
        return {
            "portfolio_return": only["portfolio_return"],
            "benchmark_return": only["benchmark_return"],
            "active_return": only["active_return"],
            "allocation": only["allocation"],
            "selection": only["selection"],
            "interaction": only["interaction"],
            "groups": only["groups"],
        }

    if method == "sum":
        allocation = sum(p["allocation"] for p in periods)
        selection = sum(p["selection"] for p in periods)
        interaction = sum(p["interaction"] for p in periods)
        return {
            "portfolio_return": _compound(p["portfolio_return"] for p in periods),
            "benchmark_return": _compound(p["benchmark_return"] for p in periods),
            "active_return": allocation + selection + interaction,
            "allocation": allocation,
            "selection": selection,
            "interaction": interaction,
            "groups": _sum_groups(periods, scale=None),
        }

    port_rets = [p["portfolio_return"] for p in periods]
    bench_rets = [p["benchmark_return"] for p in periods]
    scales = [_grap_scale(index, port_rets, bench_rets) for index in range(len(periods))]
    allocation = sum(p["allocation"] * scales[i] for i, p in enumerate(periods))
    selection = sum(p["selection"] * scales[i] for i, p in enumerate(periods))
    interaction = sum(p["interaction"] * scales[i] for i, p in enumerate(periods))
    wealth_p = _prod_growth(port_rets)
    wealth_b = _prod_growth(bench_rets)
    return {
        "portfolio_return": wealth_p - 1.0,
        "benchmark_return": wealth_b - 1.0,
        # GRAP 链接后的超额 = 期末财富差（起点为 1）
        "active_return": wealth_p - wealth_b,
        "allocation": allocation,
        "selection": selection,
        "interaction": interaction,
        "groups": _sum_groups(periods, scale=scales),
    }


def _grap_scale(index: int, port_rets: list[float], bench_rets: list[float]) -> float:
    pre = 1.0
    for value in port_rets[:index]:
        pre *= 1.0 + value
    post = 1.0
    for value in bench_rets[index + 1 :]:
        post *= 1.0 + value
    return pre * post


def _prod_growth(returns: list[float]) -> float:
    growth = 1.0
    for value in returns:
        growth *= 1.0 + value
    return growth


def _compound(returns) -> float:
    return _prod_growth(list(returns)) - 1.0


def _sum_groups(periods: list[dict[str, Any]], scale: list[float] | None) -> list[dict[str, Any]]:
    bucket: dict[str, dict[str, float]] = {}
    for index, period in enumerate(periods):
        factor = 1.0 if scale is None else scale[index]
        for row in period["groups"]:
            item = bucket.setdefault(
                row["group"],
                {
                    "group": row["group"],
                    "portfolio_weight": 0.0,
                    "benchmark_weight": 0.0,
                    "portfolio_return": 0.0,
                    "benchmark_return": 0.0,
                    "allocation": 0.0,
                    "selection": 0.0,
                    "interaction": 0.0,
                    "active": 0.0,
                    "_n": 0.0,
                },
            )
            item["portfolio_weight"] += row["portfolio_weight"]
            item["benchmark_weight"] += row["benchmark_weight"]
            item["portfolio_return"] += row["portfolio_return"]
            item["benchmark_return"] += row["benchmark_return"]
            item["allocation"] += row["allocation"] * factor
            item["selection"] += row["selection"] * factor
            item["interaction"] += row["interaction"] * factor
            item["active"] += row["active"] * factor
            item["_n"] += 1.0
    rows = []
    for item in bucket.values():
        n = item.pop("_n") or 1.0
        item["portfolio_weight"] /= n
        item["benchmark_weight"] /= n
        item["portfolio_return"] /= n
        item["benchmark_return"] /= n
        rows.append(item)
    rows.sort(key=lambda row: abs(row["active"]), reverse=True)
    return rows
