"""个券收益贡献（Single Security Contribution to Return）。

核心：
  C_i = W_i × R_i

场景：
1. 静态单期：期初权重 × 当期收益率；Σ C_i = R_p（加现金/其他残差）
2. 多期近似：平均权重 × 累计收益率
3. 每日估值链式：C_{i,t} = W_{i,t-1} × R_{i,t}，再用 Carino / Menchero / 直接相加 链接到区间

Carino（对数平滑，行业常用）：
  κ_t = ln(1+R_{p,t}) / R_{p,t}   (R_{p,t}=0 时取 1)
  κ   = ln(1+R_p) / R_p           (R_p=0 时取 1)
  C_i = (1/κ) × Σ_t (κ_t × C_{i,t})
  保证 Σ C_i = R_p = Π(1+R_{p,t}) - 1

Menchero（等权缩放因子）：
  先算各期算术贡献，再乘统一缩放使加总等于几何组合收益。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import log
from typing import Any, Literal

LinkMethod = Literal["carino", "menchero", "sum"]
Mode = Literal["single", "average", "daily"]


def contribution(
    positions: list[dict[str, Any]],
    *,
    mode: Mode = "single",
    link_method: LinkMethod = "carino",
    group_by: str = "symbol",
    portfolio_return: float | None = None,
) -> dict[str, Any]:
    """计算个券/分组收益贡献。

    positions 每行：
      date, symbol, weight, return_period,
      asset?, industry?, security_name?
    weight / return_period 均为小数。同一 date 为一期；
    daily 模式下 weight 视为该期期初权重。
    """
    if group_by not in {"symbol", "asset", "industry", "portfolio"}:
        raise ValueError(f"unsupported group_by: {group_by}")
    if mode not in {"single", "average", "daily"}:
        raise ValueError(f"unsupported mode: {mode}")
    if link_method not in {"carino", "menchero", "sum"}:
        raise ValueError(f"unsupported link_method: {link_method}")

    by_date = _by_date(positions)
    dates = sorted(by_date)
    if not dates:
        return _empty(mode, link_method, group_by)

    if mode == "average":
        return _present(_average(positions, group_by), mode, "average", group_by, portfolio_return)

    if mode == "single":
        # 静态单期：用最早一期的期初权重 × 该行已准备好的区间收益率
        linked = _single(by_date[dates[0]], group_by, dates[0])
        return _present(linked, mode, "single", group_by, portfolio_return)

    period_results = [_single(by_date[day], group_by, day) for day in dates]
    if len(period_results) == 1:
        return _present(period_results[0], mode, "single", group_by, portfolio_return)
    linked = _link(period_results, link_method)
    return _present(linked, mode, link_method, group_by, portfolio_return)


def carino_factors(period_returns: list[float]) -> tuple[list[float], float]:
    """返回各期 κ_t 与整体 1/κ 缩放，使算术效应链接到几何总收益。"""
    growth = 1.0
    kappas: list[float] = []
    for ret in period_returns:
        growth *= 1.0 + ret
        kappas.append(_kappa(ret))
    total = growth - 1.0
    overall = _kappa(total)
    scale = 1.0 / overall if overall else 1.0
    return kappas, scale


def _kappa(ret: float) -> float:
    if abs(ret) < 1e-15:
        return 1.0
    return log(1.0 + ret) / ret


def _empty(mode: str, link_method: str, group_by: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "link_method": link_method,
        "group_by": group_by,
        "portfolio_return": 0.0,
        "contribution_total": 0.0,
        "residual": 0.0,
        "groups": [],
        "periods": [],
    }


def _by_date(rows: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    out: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        day = row.get("date")
        if isinstance(day, date):
            out[day].append(row)
    return out


def _label(row: dict[str, Any], group_by: str) -> str:
    if group_by == "portfolio":
        return "PORTFOLIO"
    if group_by == "asset":
        return str(row.get("asset") or "其他")
    if group_by == "industry":
        return str(row.get("industry") or "未分类")
    return str(row.get("symbol") or "UNKNOWN")


def _single(rows: list[dict[str, Any]], group_by: str, day: date) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    portfolio_return = 0.0
    contribution_total = 0.0
    for row in rows:
        weight = float(row.get("weight") or 0.0)
        ret = float(row.get("return_period") or 0.0)
        contrib = weight * ret
        portfolio_return += contrib
        contribution_total += contrib
        label = _label(row, group_by)
        bucket = grouped.setdefault(
            label,
            {
                "group": label,
                "symbol": str(row.get("symbol") or label),
                "security_name": str(row.get("security_name") or row.get("symbol") or label),
                "asset": str(row.get("asset") or ""),
                "industry": str(row.get("industry") or ""),
                "weight": 0.0,
                "return_period": 0.0,
                "contribution": 0.0,
                "weight_sum": 0.0,
            },
        )
        bucket["weight"] += weight
        bucket["contribution"] += contrib
        bucket["weight_sum"] += weight
        # 组内收益：贡献 / 组权重
    groups = []
    for bucket in grouped.values():
        w = bucket["weight"]
        bucket["return_period"] = (bucket["contribution"] / w) if abs(w) > 1e-15 else 0.0
        groups.append(
            {
                "group": bucket["group"],
                "symbol": bucket["symbol"],
                "security_name": bucket["security_name"],
                "asset": bucket["asset"],
                "industry": bucket["industry"],
                "weight": bucket["weight"],
                "return_period": bucket["return_period"],
                "contribution": bucket["contribution"],
            }
        )
    groups.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    return {
        "date": day.isoformat(),
        "portfolio_return": portfolio_return,
        "contribution_total": contribution_total,
        "groups": groups,
    }


def _average(rows: list[dict[str, Any]], group_by: str) -> dict[str, Any]:
    """平均权重 × 累计收益：按 symbol 聚合后再按 group_by 汇总。"""
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("symbol") or "UNKNOWN")
        item = by_symbol.setdefault(
            key,
            {
                "symbol": key,
                "security_name": str(row.get("security_name") or key),
                "asset": str(row.get("asset") or ""),
                "industry": str(row.get("industry") or ""),
                "weight_sum": 0.0,
                "n": 0,
                "growth": 1.0,
            },
        )
        item["weight_sum"] += float(row.get("weight") or 0.0)
        item["n"] += 1
        item["growth"] *= 1.0 + float(row.get("return_period") or 0.0)
        if row.get("security_name"):
            item["security_name"] = str(row["security_name"])
        if row.get("asset"):
            item["asset"] = str(row["asset"])
        if row.get("industry"):
            item["industry"] = str(row["industry"])

    expanded = []
    day = next((row.get("date") for row in rows if isinstance(row.get("date"), date)), date.today())
    for item in by_symbol.values():
        n = item["n"] or 1
        avg_w = item["weight_sum"] / n
        cum_r = item["growth"] - 1.0
        expanded.append(
            {
                "date": day,
                "symbol": item["symbol"],
                "security_name": item["security_name"],
                "asset": item["asset"],
                "industry": item["industry"],
                "weight": avg_w,
                "return_period": cum_r,
            }
        )
    return _single(expanded, group_by, day)


def _link(periods: list[dict[str, Any]], method: LinkMethod) -> dict[str, Any]:
    period_returns = [float(p["portfolio_return"]) for p in periods]
    growth = 1.0
    for ret in period_returns:
        growth *= 1.0 + ret
    geometric = growth - 1.0

    if method == "sum":
        factors = [1.0] * len(periods)
        scale = 1.0
    elif method == "carino":
        kappas, scale = carino_factors(period_returns)
        factors = kappas
    else:
        # Menchero：统一缩放，使 Σ_t C_{i,t} * α = 几何总收益在个券上的分摊
        arithmetic = sum(period_returns)
        if abs(arithmetic) < 1e-15:
            factors = [1.0] * len(periods)
            scale = 1.0
        else:
            alpha = geometric / arithmetic
            factors = [alpha] * len(periods)
            scale = 1.0

    labels = {row["group"] for period in periods for row in period["groups"]}
    groups = []
    for label in labels:
        contrib = 0.0
        weight_acc = 0.0
        ret_proxy = 0.0
        meta = None
        for index, period in enumerate(periods):
            row = next((item for item in period["groups"] if item["group"] == label), None)
            if not row:
                continue
            meta = row
            contrib += scale * factors[index] * float(row["contribution"])
            weight_acc += float(row["weight"])
            ret_proxy += float(row["return_period"])
        if meta is None:
            continue
        n = len(periods) or 1
        avg_w = weight_acc / n
        groups.append(
            {
                "group": label,
                "symbol": meta["symbol"],
                "security_name": meta["security_name"],
                "asset": meta["asset"],
                "industry": meta["industry"],
                "weight": avg_w,
                "return_period": (contrib / avg_w) if abs(avg_w) > 1e-15 else ret_proxy / n,
                "contribution": contrib,
            }
        )
    groups.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    contribution_total = sum(item["contribution"] for item in groups)
    return {
        "date": periods[-1]["date"],
        "portfolio_return": geometric if method != "sum" else sum(period_returns),
        "contribution_total": contribution_total,
        "groups": groups,
        "period_count": len(periods),
    }


def _present(
    linked: dict[str, Any],
    mode: str,
    link_method: str,
    group_by: str,
    portfolio_return: float | None,
) -> dict[str, Any]:
    measured = float(linked["portfolio_return"])
    target = measured if portfolio_return is None else float(portfolio_return)
    contribution_total = float(linked["contribution_total"])
    residual = target - contribution_total
    return {
        "mode": mode,
        "link_method": link_method,
        "group_by": group_by,
        "portfolio_return": target,
        "contribution_total": contribution_total,
        "residual": residual,
        "groups": linked["groups"],
        "periods": linked.get("period_count") or 1,
    }
