"""投资风险 · 风险指标 Tab 业务模块（``/investment-risk/indicators#risk-exposure`` 核心页签）。

资管风控口径（非 UI 控件）：

1. **核心风险轮廓** — 区间收益 / 年化波动 / 最大回撤 / 股票换手 / Beta
2. **滚动波动率** — 窗口年化波动时序（供曲线与回撤摘要）
3. **VaR 三方法对比** — 历史模拟 / 蒙特卡洛 / 分布公式
4. **六大风控类型看板** — 市场 / 信用 / 流动性 / 集中度与杠杆 / 合规操作 / 产品压力

权威 NAV / 持仓仍来自 ``fsi.balance_*``；本模块在 ``RiskEngine.bind(snapshot)``
上给出可对账、可单测的同一套业务数字。换手率等需成交流水的字段经 ``meta`` 注入。
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np

from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..instruments.classify import EQUITY_LIKE, FIXED_INCOME, CASH_LIKE, issuer_name
from ..risk import kpis as _kpis

BUSINESS_MODULES = (
    "core_profile",
    "rolling_volatility",
    "var_compare",
    "metric_board",
)

RISK_CATEGORIES = (
    ("market", "市场风险", "Market Risk"),
    ("credit", "信用风险", "Credit Risk"),
    ("liquidity", "流动性风险", "Liquidity Risk"),
    ("concentration", "集中度与杠杆", "Concentration & Leverage"),
    ("compliance", "投资合规与操作风险", "Compliance & Operational Risk"),
    ("stress", "产品压力测试", "Stress Testing"),
)

# 投资级：BBB- 及以上（简化档位）
_IG_RATINGS = frozenset(
    {
        "AAA",
        "AA+",
        "AA",
        "AA-",
        "A+",
        "A",
        "A-",
        "BBB+",
        "BBB",
        "BBB-",
        "Aaa",
        "Aa1",
        "Aa2",
        "Aa3",
        "A1",
        "A2",
        "A3",
        "Baa1",
        "Baa2",
        "Baa3",
    }
)


def _nav_returns(snapshot: Any) -> np.ndarray:
    return np.asarray([float(item[1]) for item in (getattr(snapshot, "nav_returns", None) or ())], dtype=float)


def _nav_dates(snapshot: Any) -> list[date]:
    out: list[date] = []
    for item in getattr(snapshot, "nav_returns", None) or ():
        raw = item[0]
        out.append(raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10]))
    return out


def _metric(
    metric_id: str,
    name: str,
    *,
    value: Any = None,
    unit: str | None = None,
    status: str = "computed",
    note: str | None = None,
    detail: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": name,
        "group": group,
        "value": value,
        "unit": unit,
        "status": status if value is not None or status == "unavailable" else "unavailable",
        "note": note,
        "detail": detail,
    }


def _round(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def interval_return_pct(returns: np.ndarray) -> float | None:
    if returns.size == 0:
        return None
    wealth = float(np.prod(1.0 + returns) - 1.0)
    return wealth * 100.0


def max_drawdown_pack(returns: np.ndarray, dates: Sequence[date]) -> dict[str, Any]:
    if returns.size == 0:
        return {
            "max_drawdown_pct": None,
            "max_drawdown_start": None,
            "max_drawdown_end": None,
        }
    wealth = np.cumprod(1.0 + returns)
    peaks = np.maximum.accumulate(wealth)
    dd = wealth / peaks - 1.0
    idx = int(np.argmin(dd))
    peak_idx = int(np.argmax(wealth[: idx + 1])) if idx >= 0 else 0
    start = dates[peak_idx].isoformat() if peak_idx < len(dates) else None
    end = dates[idx].isoformat() if idx < len(dates) else None
    return {
        "max_drawdown_pct": float(dd[idx]) * 100.0,
        "max_drawdown_start": start,
        "max_drawdown_end": end,
    }


def module_core_profile(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict[str, Any]:
    """核心五卡：区间收益 / 年化波动 / 最大回撤 / 换手 / Beta。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    returns = _nav_returns(snapshot)
    dates = _nav_dates(snapshot)
    if period_start and dates:
        mask = [period_start <= d <= (period_end or dates[-1]) for d in dates]
        returns = returns[np.asarray(mask, dtype=bool)]
        dates = [d for d, keep in zip(dates, mask) if keep]

    vol = _kpis.kpi_volatility(snapshot)
    vol_pct = (vol["result"].get("annualized_pct") if returns.size >= 2 else None)
    # 若做了区间切片，按切片重算波动
    if returns.size >= 2 and (period_start is not None or period_end is not None):
        vol_pct = float(np.std(returns, ddof=1) * math.sqrt(252) * 100.0)

    dd = max_drawdown_pack(returns, dates)
    bench = list(getattr(snapshot, "benchmark_returns", None) or [])
    if info.get("benchmark_returns"):
        bench = [float(x) for x in info["benchmark_returns"]]
    beta_kpi = _kpis.kpi_beta(snapshot, benchmark_returns=bench or None)
    beta_value = beta_kpi["result"].get("beta")

    turnover_meta = dict(info.get("equity_turnover") or {})
    equity_turnover = {
        "buy_amount": float(turnover_meta.get("buy_amount") or 0.0),
        "sell_amount": float(turnover_meta.get("sell_amount") or 0.0),
        "average_equity_balance": float(turnover_meta.get("average_equity_balance") or 0.0),
        "period_turnover_pct": turnover_meta.get("period_turnover_pct"),
        "annualized_turnover_pct": turnover_meta.get("annualized_turnover_pct"),
        "method": turnover_meta.get("method")
        or "单边换手率=min(买入额,卖出额)/区间日均股票余额",
    }
    if (
        equity_turnover["annualized_turnover_pct"] is None
        and equity_turnover["average_equity_balance"] > 0
    ):
        period = min(equity_turnover["buy_amount"], equity_turnover["sell_amount"]) / equity_turnover[
            "average_equity_balance"
        ]
        equity_turnover["period_turnover_pct"] = period * 100.0
        # 粗略年化：按日历窗长度，缺省按 1 年
        days = max(len(returns), 1)
        equity_turnover["annualized_turnover_pct"] = period * (252.0 / days) * 100.0

    as_of = snapshot.as_of_date.isoformat()
    start = dates[0].isoformat() if dates else (period_start.isoformat() if period_start else as_of)
    end = dates[-1].isoformat() if dates else (period_end.isoformat() if period_end else as_of)

    return {
        "module": "core_profile",
        "fund_id": str(snapshot.fund_id),
        "period_start": start,
        "period_end": end,
        "resolved_period_start": start,
        "resolved_period_end": end,
        "data_as_of": as_of,
        "interval_return_pct": _round(interval_return_pct(returns), 3),
        "annualized_volatility_pct": _round(vol_pct, 3),
        "max_drawdown_pct": _round(dd["max_drawdown_pct"], 3),
        "max_drawdown_start": dd["max_drawdown_start"],
        "max_drawdown_end": dd["max_drawdown_end"],
        "sample_size": int(returns.size),
        "equity_turnover": equity_turnover,
        "equity_beta": {
            "value": _round(beta_value, 3),
            "benchmark_id": info.get("benchmark_id") or getattr(snapshot, "benchmark_id", None),
            "sample_size": int(beta_kpi["result"].get("paired_observations") or 0),
            "constituents": list(info.get("beta_constituents") or ()),
        },
        "message": None if returns.size else "无可用 NAV 收益序列",
        "formulas": {
            "interval_return": "Π(1+r_t) − 1",
            "volatility": "stdev(r)×√252",
            "max_drawdown": "min(W_t / peak_t − 1)",
            "beta": "Cov(R_p,R_b)/Var(R_b)",
        },
    }


def module_rolling_volatility(
    bound: Any,
    *,
    window: int = 20,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict[str, Any]:
    """滚动年化波动率时序（与页面 SQL-RI-02 / 趋势图对齐）。"""

    snapshot = bound.snapshot
    returns = _nav_returns(snapshot)
    dates = _nav_dates(snapshot)
    points: list[dict[str, Any]] = []
    win = max(int(window), 2)
    for index in range(len(returns)):
        day = dates[index] if index < len(dates) else snapshot.as_of_date
        if period_start and day < period_start:
            continue
        if period_end and day > period_end:
            continue
        start = max(0, index - win + 1)
        slice_ = returns[start : index + 1]
        rolling = None
        if slice_.size >= 2:
            rolling = float(np.std(slice_, ddof=1) * math.sqrt(252) * 100.0)
        wealth = float(np.prod(1.0 + returns[: index + 1]))
        peak = float(np.max(np.cumprod(1.0 + returns[: index + 1]))) if index >= 0 else wealth
        drawdown_pct = (wealth / peak - 1.0) * 100.0 if peak else None
        points.append(
            {
                "date": day.isoformat(),
                "rolling_volatility_pct": _round(rolling, 4),
                "drawdown_pct": _round(drawdown_pct, 4),
                "window": win,
            }
        )
    return {
        "module": "rolling_volatility",
        "window": win,
        "points": points,
        "count": len(points),
        "formula": "σ_t = stdev(r_{t−w+1…t}) × √252 × 100",
    }


def _var_row(
    *,
    method: str,
    method_requested: str,
    var_return: float | None,
    cvar_return: float | None,
    nav: float,
    confidence: float,
    sample_size: int,
    status: str = "OK",
) -> dict[str, Any]:
    var_pct = abs(float(var_return)) * 100.0 if var_return is not None else None
    cvar_pct = abs(float(cvar_return)) * 100.0 if cvar_return is not None else None
    return {
        "method": method,
        "method_requested": method_requested,
        "status": status,
        "confidence": confidence,
        "sample_size": sample_size,
        "var_return": var_return,
        "cvar_return": cvar_return,
        "var_pct_nav": var_pct,
        "cvar_pct_nav": cvar_pct,
        "var_hkd": abs(float(var_return) * nav) if var_return is not None else None,
        "cvar_hkd": abs(float(cvar_return) * nav) if cvar_return is not None else None,
    }


def module_var_compare(
    bound: Any,
    *,
    confidence: float = 0.99,
    horizon_days: int = 1,
    simulations: int = 5_000,
    seed: int = 42,
) -> dict[str, Any]:
    """VaR 三方法：历史模拟 / 蒙特卡洛 / 分布公式（参数法）。"""

    snapshot = bound.snapshot
    nav = float(snapshot.net_asset or 0.0)
    returns = _nav_returns(snapshot)
    n = int(returns.size)
    results: list[dict[str, Any]] = []

    # 1) 历史模拟
    hist = bound.engine.riskfolio.historical_var_cvar(returns, confidence)
    if hist.get("status") == "OK" and hist.get("var") is not None:
        # horizon 粗调：日度 × √h
        scale = math.sqrt(max(horizon_days, 1))
        results.append(
            _var_row(
                method="HISTORICAL_SIMULATION",
                method_requested="historical",
                var_return=float(hist["var"]) * scale,
                cvar_return=(None if hist.get("cvar") is None else float(hist["cvar"]) * scale),
                nav=nav,
                confidence=confidence,
                sample_size=n,
            )
        )
    else:
        results.append(
            _var_row(
                method="HISTORICAL_SIMULATION",
                method_requested="historical",
                var_return=None,
                cvar_return=None,
                nav=nav,
                confidence=confidence,
                sample_size=n,
                status="INSUFFICIENT_DATA",
            )
        )

    # 2) 分布公式（正态）
    if n >= 2 and float(np.std(returns, ddof=1)) > 0:
        mu = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))
        # 标准正态分位：用 erfinv 近似，避免硬依赖 scipy
        # Φ^{-1}(p) ≈ √2 · erfinv(2p−1)；此处用 numpy 无现成 erfinv 时退回历史分位
        try:
            from scipy.stats import norm  # type: ignore

            z = float(norm.ppf(1.0 - confidence))
            pdf = float(norm.pdf(z))
        except Exception:
            # 0.99 → ≈ -2.326；0.95 → ≈ -1.645
            z = -2.326347874 if confidence >= 0.99 else -1.644853627
            pdf = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
        h = max(horizon_days, 1)
        var_pct = -(mu * h + z * sigma * math.sqrt(h))
        cvar_pct = -(mu * h - sigma * math.sqrt(h) * pdf / max(1.0 - confidence, 1e-9))
        results.append(
            _var_row(
                method="DISTRIBUTION_FORMULA",
                method_requested="distribution",
                var_return=-abs(var_pct),
                cvar_return=-abs(cvar_pct),
                nav=nav,
                confidence=confidence,
                sample_size=n,
            )
        )
    else:
        results.append(
            _var_row(
                method="DISTRIBUTION_FORMULA",
                method_requested="distribution",
                var_return=None,
                cvar_return=None,
                nav=nav,
                confidence=confidence,
                sample_size=n,
                status="INSUFFICIENT_DATA",
            )
        )

    # 3) 蒙特卡洛
    if n >= 2 and float(np.std(returns, ddof=1)) > 0:
        rng = np.random.default_rng(seed)
        mu = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))
        h = max(horizon_days, 1)
        sims = rng.normal(mu * h, sigma * math.sqrt(h), size=int(simulations))
        alpha = (1.0 - confidence) * 100.0
        var_r = float(np.percentile(sims, alpha))
        tail = sims[sims <= var_r]
        cvar_r = float(np.mean(tail)) if tail.size else var_r
        results.append(
            _var_row(
                method="MONTE_CARLO",
                method_requested="monte_carlo",
                var_return=var_r,
                cvar_return=cvar_r,
                nav=nav,
                confidence=confidence,
                sample_size=int(simulations),
            )
        )
    else:
        results.append(
            _var_row(
                method="MONTE_CARLO",
                method_requested="monte_carlo",
                var_return=None,
                cvar_return=None,
                nav=nav,
                confidence=confidence,
                sample_size=0,
                status="INSUFFICIENT_DATA",
            )
        )

    pcts = [row["var_pct_nav"] for row in results if row.get("var_pct_nav") is not None]
    return {
        "module": "var_compare",
        "fund_id": str(snapshot.fund_id),
        "as_of_date": snapshot.as_of_date.isoformat(),
        "confidence": confidence,
        "horizon_days": horizon_days,
        "results": results,
        "max_var_pct_nav": max(pcts) if pcts else 0.0,
        "note": "三方法均基于 NAV 日收益；金额 = |VaR_return| × NAV",
    }


def _bond_positions(snapshot: Any) -> list[Any]:
    return [p for p in snapshot.positions if (p.asset_class or "") in FIXED_INCOME]


def _equity_positions(snapshot: Any) -> list[Any]:
    return [p for p in snapshot.positions if (p.asset_class or "") in EQUITY_LIKE]


def _rating_of(position: Any, *, field: str = "rating") -> str:
    meta = dict(getattr(position, "metadata", None) or {})
    raw = meta.get(field) or meta.get("debt_rating") or meta.get("issuer_rating") or meta.get("rating") or "NR"
    return str(raw).strip() or "NR"


def _rating_distribution(positions: Sequence[Any], nav: float, *, field: str) -> list[dict[str, Any]]:
    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        buckets[_rating_of(position, field=field)] += abs(float(position.market_value_base or 0.0))
    total = sum(buckets.values()) or 1.0
    rows = []
    for rating, mv in sorted(buckets.items(), key=lambda item: abs(item[1]), reverse=True):
        rows.append(
            {
                "rating": rating,
                "market_value": mv,
                "weight_pct": mv / total * 100.0,
                "is_investment_grade": rating in _IG_RATINGS,
            }
        )
    return rows


def _ig_pct(dist: Sequence[Mapping[str, Any]]) -> float | None:
    if not dist:
        return None
    return sum(float(row["weight_pct"]) for row in dist if row.get("is_investment_grade"))


def _top_pct(positions: Sequence[Any], nav: float, n: int) -> float | None:
    if not positions or not nav:
        return None
    ordered = sorted(positions, key=lambda p: abs(float(p.market_value_base or 0.0)), reverse=True)
    return sum(abs(float(p.market_value_base or 0.0)) for p in ordered[:n]) / nav * 100.0


def _hhi(positions: Sequence[Any], nav: float) -> float | None:
    if not positions or not nav:
        return None
    weights = [abs(float(p.market_value_base or 0.0)) / nav for p in positions]
    return sum(w * w for w in weights) * 10_000.0


def _issuer_hhi(positions: Sequence[Any], nav: float) -> tuple[float | None, float | None]:
    if not positions or not nav:
        return None, None
    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        buckets[issuer_name(position)] += abs(float(position.market_value_base or 0.0))
    weights = [mv / nav for mv in buckets.values()]
    hhi = sum(w * w for w in weights) * 10_000.0
    top = max(weights) * 100.0 if weights else None
    return hhi, top


def _ext(info: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """优先 meta.extensions，再扁平 meta。"""

    extensions = dict(info.get("extensions") or {})
    for key in keys:
        if key in extensions and extensions[key] is not None:
            return extensions[key]
        if key in info and info[key] is not None:
            return info[key]
    return default


def _ams_metric(
    metric_id: str,
    name: str,
    value: Any,
    *,
    limit: float,
    op: str,
    unit: str,
    ams_code: str,
    hard: bool = True,
    scheme: str = "BAMUSDMMF风控001",
    group: str = "货基 AMS",
    applicable: bool = True,
) -> dict[str, Any]:
    hard_label = "硬指标" if hard else "内部从严"
    limit_txt = f"{op}{limit}{unit}"
    note = f"AMS {ams_code} · {scheme} · {hard_label} · 限额 {limit_txt}"
    if not applicable or value is None:
        return _metric(metric_id, name, value=None, unit=unit, status="unavailable", note=note, group=group)
    num = float(value)
    breached = (num > limit) if op == "<=" else (num < limit) if op == ">=" else (num >= limit)
    status_word = "超限" if breached else "合规"
    return _metric(
        metric_id,
        name,
        value=_round(num, 2 if unit == "%" else 1),
        unit=unit,
        status="computed",
        note=f"{status_word} · {note}",
        group=group,
    )


def _country_concentration(positions: Sequence[Any], nav: float) -> tuple[float | None, str | None]:
    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        meta = dict(getattr(position, "metadata", None) or {})
        country = str(meta.get("country") or meta.get("region") or meta.get("market_id") or "UN").upper()
        # 常见市场代码归一
        if country in {"XHKG", "HKG", "HK"}:
            country = "HK"
        elif country in {"XSHG", "XSHE", "CN", "CHN"}:
            country = "CN"
        elif country in {"XNYS", "XNAS", "US", "USA"}:
            country = "US"
        buckets[country] += abs(float(position.market_value_base or 0.0))
    if not buckets or not nav:
        return None, None
    ordered = sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    top_pct = ordered[0][1] / nav * 100.0
    detail = ", ".join(f"{code} {mv / nav * 100.0:.1f}%" for code, mv in ordered[:5])
    return top_pct, detail


def _controller_concentration(positions: Sequence[Any]) -> tuple[float | None, str | None]:
    buckets: dict[str, float] = defaultdict(float)
    for position in positions:
        meta = dict(getattr(position, "metadata", None) or {})
        ctrl = str(
            meta.get("actual_controller_id")
            or meta.get("controller")
            or meta.get("issuer_group")
            or meta.get("issuer")
            or issuer_name(position)
        )
        buckets[ctrl] += abs(float(position.market_value_base or 0.0))
    total = sum(buckets.values())
    if not total:
        return None, None
    top_name, top_mv = max(buckets.items(), key=lambda item: item[1])
    return top_mv / total * 100.0, top_name


def _ttl_from_rows(rows: Sequence[Mapping[str, Any]], nav: float) -> dict[str, Any]:
    """由流动性桶行估算 TTL / 超期占比 / 分资产类变现天数。"""

    if not rows or not nav:
        return {
            "avg_ttl": None,
            "bond_ttl": None,
            "stock_ttl": None,
            "over_10d_pct": None,
            "over_40d_pct": None,
            "ttl_10": None,
            "ttl_25": None,
            "ttl_50": None,
        }
    # 桶 → 代表天数
    bucket_days = {"T0": 0.0, "1W": 5.0, "1M": 20.0, "3M": 60.0, "6M": 120.0, "ILLIQUID": 180.0}
    weighted = 0.0
    bond_w = stock_w = 0.0
    bond_d = stock_d = 0.0
    over_10 = over_40 = 0.0
    ladder: list[tuple[float, float]] = []  # (days, mv)
    for row in rows:
        mv = abs(float(row.get("base_pv") or 0.0))
        days = float(row.get("days") or bucket_days.get(str(row.get("bucket")), 30.0))
        # 若有显式 days 用显式；上市股权默认 5 天
        klass = str(row.get("asset_class") or "")
        if klass in {"EQUITY", "ETF"} and not row.get("days"):
            days = 5.0
        weighted += mv * days
        ladder.append((days, mv))
        if days > 10:
            over_10 += mv
        if days > 40:
            over_40 += mv
        if klass in FIXED_INCOME or klass in {"BOND", "CD", "DEPOSIT"}:
            bond_w += mv
            bond_d += mv * days
        if klass in {"EQUITY", "ETF"}:
            stock_w += mv
            stock_d += mv * days
    total_mv = sum(mv for _, mv in ladder) or 1.0
    ladder.sort(key=lambda item: item[0])
    # TTL k%：累计可变现达到组合 NAV 的 k% 所需天数
    def _ttl_at(pct: float) -> float | None:
        need = nav * pct / 100.0
        acc = 0.0
        for days, mv in ladder:
            acc += mv
            if acc >= need:
                return days
        return ladder[-1][0] if ladder else None

    return {
        "avg_ttl": weighted / total_mv if total_mv else None,
        "bond_ttl": (bond_d / bond_w) if bond_w else None,
        "stock_ttl": (stock_d / stock_w) if stock_w else None,
        "over_10d_pct": over_10 / nav * 100.0,
        "over_40d_pct": over_40 / nav * 100.0,
        "ttl_10": _ttl_at(10.0),
        "ttl_25": _ttl_at(25.0),
        "ttl_50": _ttl_at(50.0),
    }


# 页面六大类应对齐的指标 id（缺口用 meta.extensions 补）
REQUIRED_METRIC_IDS: dict[str, tuple[str, ...]] = {
    "market": (
        "interval_return",
        "day_return",
        "annualized_vol",
        "max_drawdown",
        "equity_beta",
        "sharpe",
        "info_ratio",
        "tracking_error",
        "duration",
        "modified_duration",
        "convexity",
        "dv01",
        "avg_remaining",
        "credit_spread",
        "turnover",
        "style_deviation",
        "avg_pe",
        "avg_pb",
        "factor_equity_exposure",
        "factor_rate_credit_exposure",
        "factor_fx_exposure",
        "factor_beta",
        "factor_tracking_error",
        "fx_exposure",
        "non_cny_pct",
        "country_conc",
        "rolling_vol_latest",
        "daily_var_pct",
    ),
    "credit": (
        "issuer_rating_dist",
        "debt_rating_dist",
        "issuer_ig_pct",
        "issuer_below_ig_pct",
        "debt_ig_pct",
        "debt_below_ig_pct",
        "issuer_hhi",
        "top_issuer_pct",
        "bond_top5",
        "bond_top10",
        "cs01",
        "implied_pd",
        "neg_news",
        "controller_conc",
    ),
    "liquidity": (
        "ttl_10",
        "ttl_25",
        "ttl_50",
        "avg_ttl",
        "stock_ttl",
        "bond_ttl",
        "over_10d",
        "over_40d",
        "cash_pct",
        "cash_only",
        "lcr_15",
        "rate_bond_pct",
        "restricted_pct",
        "net_redemption",
        "investor_conc",
    ),
    "concentration": (
        "equity_top5",
        "equity_top10",
        "equity_largest",
        "equity_hhi",
        "sector_hhi",
        "bond_conc_top10",
        "issuer_top",
        "leverage",
        "repo_pct",
        "country_qdii",
        "controller_eq",
        "equity_float",
    ),
    "compliance": (
        "ams_wam",
        "ams_wal",
        "ams_wla",
        "ams_wam_internal",
        "ams_wal_internal",
        "ams_wla_internal",
        "ams_single_issuer",
        "process_exceptions",
        "counterparty_limit_usage",
        "regulatory_redlines",
        "related_party_pct",
        "deposit_bank_usage",
    ),
    "stress": (
        "rate_shock_50",
        "rate_shock_50_pct",
        "redemption_15_lcr",
        "redemption_20_lcr",
        "market_crash_nav",
        "credit_default_3",
        "top5_investor_redeem",
    ),
}


def module_metric_board(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    core: Mapping[str, Any] | None = None,
    confidence: float = 0.99,
) -> dict[str, Any]:
    """六大风控类型看板：对齐页面 metric-board 全量指标清单。"""

    snapshot = bound.snapshot
    info = dict(meta or {})
    nav = float(snapshot.net_asset or 0.0) or 1.0
    base_ccy = str(snapshot.reporting_currency or "HKD").upper()
    core_pack = dict(core or module_core_profile(bound, meta=meta))
    bonds = _bond_positions(snapshot)
    equities = _equity_positions(snapshot)
    bond_mv = sum(abs(float(p.market_value_base or 0.0)) for p in bonds)
    cash_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in snapshot.positions
        if (p.asset_class or "") in CASH_LIKE or (p.asset_class or "") == "DEPOSIT"
    )
    repo_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in snapshot.positions
        if (p.asset_class or "") in {"REPO"}
    )
    rate_bond_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in bonds
        if str((getattr(p, "metadata", None) or {}).get("bond_subtype")
               or (getattr(p, "metadata", None) or {}).get("sector")
               or "").upper()
        in {"BOND_GOVT", "GOVT", "TREASURY", "SOVEREIGN", "利率债", "国债"}
        or str(getattr(p, "security_code", "")).upper().startswith(("TBILL", "GOVT", "UST"))
    )

    duration = _kpis.kpi_duration(snapshot)["result"].get("weighted_years")
    dv01 = _kpis.kpi_dv01(snapshot)["result"]
    cs01 = _kpis.kpi_cs01(snapshot)["result"]
    # kpi_factor_exposure.result 即为 {FACTOR: {amount, pct_nav}, ...}
    factor = dict(_kpis.kpi_factor_exposure(snapshot)["result"] or {})
    leverage = _kpis.kpi_leverage(snapshot)["result"].get("ratio")
    liq_kpi = _kpis.kpi_liquidity(snapshot)["result"]
    try:
        liq_report = bound.liquidity().report(redemption_pct=15.0)
    except Exception:
        liq_report = {}
    redemption = dict(liq_report.get("redemption") or {})
    buckets = dict(liq_report.get("buckets") or {})
    mmf = dict(liq_report.get("mmf") or {})
    liq_rows = list(liq_report.get("positions") or [])
    ttl = _ttl_from_rows(liq_rows, nav)

    issuer_dist = _rating_distribution(bonds, nav, field="issuer_rating")
    debt_dist = _rating_distribution(bonds, nav, field="debt_rating")
    issuer_hhi, top_issuer = _issuer_hhi(bonds, nav)
    equity_hhi = _hhi(equities, nav)
    sector_buckets: dict[str, float] = defaultdict(float)
    for position in equities:
        meta_p = dict(getattr(position, "metadata", None) or {})
        sector = str(meta_p.get("sector") or meta_p.get("industry") or "未分类")
        sector_buckets[sector] += abs(float(position.market_value_base or 0.0))
    sector_weights = [mv / nav for mv in sector_buckets.values()]
    sector_hhi = sum(w * w for w in sector_weights) * 10_000.0 if sector_weights else None

    convexity = None
    avg_remaining = None
    credit_spread_proxy = None
    if bonds:
        c_num = sum(
            abs(float(p.market_value_base or 0.0)) * float(getattr(p, "convexity", 0.0) or 0.0) for p in bonds
        )
        convexity = c_num / bond_mv if bond_mv else None
        rem = []
        ytm_w = 0.0
        for p in bonds:
            years = float(getattr(p, "duration", 0.0) or 0.0)
            mat = getattr(p, "maturity_date", None)
            if mat is not None:
                years = max((mat - snapshot.as_of_date).days / 365.0, 0.0)
            mv = abs(float(p.market_value_base or 0.0))
            rem.append(years * mv)
            ytm_w += mv * float(getattr(p, "ytm", 0.0) or 0.0)
        avg_remaining = sum(rem) / bond_mv if bond_mv else None
        # 信用利差代理：加权 YTM − 2%（无 mktdata 时）
        if bond_mv:
            credit_spread_proxy = max(ytm_w / bond_mv * 100.0 - 2.0, 0.0)

    credit_spread = _ext(info, "credit_spread", default=credit_spread_proxy)
    beta = (core_pack.get("equity_beta") or {}).get("value")
    factor_beta = _ext(info, "factor_beta", default=beta)
    market_crash = _round(beta * (-20.0), 2) if beta is not None else None
    credit_default = _round((bond_mv * 0.03) / nav * 100.0, 3) if nav else None

    rate_shock_pnl = None
    try:
        from ..core.contracts import RiskFactorType, Shock, ShockMode

        shock = Shock(RiskFactorType.RATE, 0.005, ShockMode.ABSOLUTE, label="rate_+50bp")
        priced = bound.valuation().revalue((shock,), view="LOOK_THROUGH")
        rate_shock_pnl = float(priced.pnl)
    except Exception:
        rate_shock_pnl = -(float(duration or 0.0) * 0.005 * bond_mv) if duration else None
    rate_impact = _round(abs(rate_shock_pnl) / nav * 100.0, 3) if rate_shock_pnl is not None else None

    high_liq_pct = liq_kpi.get("pct_nav")
    # 优先用流动性桶 T0+1W+1M
    if liq_report.get("liquid_pct_nav") is not None:
        high_liq_pct = float(liq_report["liquid_pct_nav"])
    lcr_15 = (high_liq_pct / 15.0) if high_liq_pct is not None else None
    lcr_20 = (high_liq_pct / 20.0) if high_liq_pct is not None else None
    # WLA ≈ T0+1W 占 NAV
    wla_pct = None
    if buckets:
        wla_pv = float((buckets.get("T0") or {}).get("base_pv") or 0.0) + float(
            (buckets.get("1W") or {}).get("base_pv") or 0.0
        )
        wla_pct = wla_pv / nav * 100.0
    wla_pct = _ext(info, "weekly_liquid_pct", "wla_pct", default=wla_pct)

    day_return = None
    rets = _nav_returns(snapshot)
    if rets.size:
        day_return = float(rets[-1]) * 100.0

    sharpe = tracking_error = info_ratio = None
    if rets.size >= 2:
        vol = float(np.std(rets, ddof=1))
        mean_r = float(np.mean(rets))
        if vol > 0:
            sharpe = (mean_r / vol) * math.sqrt(252)
    bench = list(getattr(snapshot, "benchmark_returns", None) or info.get("benchmark_returns") or [])
    bench_id = info.get("benchmark_id") or getattr(snapshot, "benchmark_id", None)
    if rets.size >= 2 and len(bench) >= 2:
        n = min(rets.size, len(bench))
        active = rets[-n:] - np.asarray(bench[-n:], dtype=float)
        te = float(np.std(active, ddof=1) * math.sqrt(252))
        tracking_error = te * 100.0
        if float(np.std(active, ddof=1)) > 0:
            info_ratio = (float(np.mean(active)) / float(np.std(active, ddof=1))) * math.sqrt(252)

    # 非本位币 / 非人民币 / 国家集中
    fx_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in snapshot.positions
        if str(getattr(p, "currency", "") or "").upper() not in {base_ccy, ""}
    )
    non_cny_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in snapshot.positions
        if str(getattr(p, "currency", "") or "").upper() not in {"CNY", "CNH", ""}
    )
    country_top, country_detail = _country_concentration(list(snapshot.positions), nav)
    ctrl_pct, ctrl_name = _controller_concentration(bonds or list(snapshot.positions))
    ctrl_pct = _ext(info, "controller_conc", default=ctrl_pct)
    ctrl_name = _ext(info, "controller_detail", default=ctrl_name)

    # 受限资产 / 流通股占比：持仓 metadata 或 extensions
    restricted_mv = sum(
        abs(float(p.market_value_base or 0.0))
        for p in equities
        if (getattr(p, "metadata", None) or {}).get("is_sellable") is False
        or (getattr(p, "metadata", None) or {}).get("is_halted")
    )
    restricted_pct = _ext(info, "restricted_pct", default=(restricted_mv / nav * 100.0 if equities else 0.0))
    equity_float = _ext(info, "equity_of_float", "equity_float")
    equity_of_shares = _ext(info, "equity_of_shares")

    style_deviation = _ext(info, "style_deviation")
    style_detail = _ext(info, "style_detail")
    avg_pe = _ext(info, "avg_pe")
    avg_pb = _ext(info, "avg_pb")
    implied_pd = _ext(info, "implied_pd")
    neg_news = _ext(info, "neg_news", default=0)
    net_redemption = _ext(info, "net_redemption")
    investor_top10 = _ext(info, "investor_top10", "investor_conc")
    investor_detail = _ext(info, "investor_detail")
    top5_cover = _ext(info, "top5_cover")
    process_exceptions = _ext(info, "process_exceptions")
    cpty_usage = _ext(info, "counterparty_limit_usage")
    redlines = _ext(info, "regulatory_redlines")
    related_party = _ext(info, "related_party_pct")
    deposit_usage = _ext(info, "deposit_bank_usage")

    # 滚动波动最新点 / 日度 VaR
    rolling_latest = None
    try:
        rolling_pts = module_rolling_volatility(bound).get("points") or []
        if rolling_pts:
            rolling_latest = rolling_pts[-1].get("rolling_volatility_pct")
    except Exception:
        rolling_latest = None
    daily_var_pct = None
    try:
        var_pack = module_var_compare(bound, confidence=confidence, horizon_days=1)
        hist = next((r for r in var_pack["results"] if r.get("method_requested") == "historical"), None)
        if hist and hist.get("var_pct_nav") is not None:
            daily_var_pct = hist["var_pct_nav"]
    except Exception:
        daily_var_pct = None

    is_mmf = bool(mmf.get("is_mmf") or info.get("is_mmf"))
    wam_days = mmf.get("wam_days")
    wal_days = mmf.get("wal_days")
    wam_internal_limit = float(_ext(info, "wam_internal_limit", default=50) or 50)
    wal_internal_limit = float(_ext(info, "wal_internal_limit", default=100) or 100)
    wla_internal_limit = float(_ext(info, "wla_internal_limit", default=20) or 20)

    te_engine = _ext(info, "factor_tracking_error", default=tracking_error)
    bench_note = f"基准 {bench_id}" if bench_id else None

    rate_bond_pct = _ext(info, "rate_bond_pct", default=(rate_bond_mv / nav * 100.0 if rate_bond_mv else 0.0))

    categories = [
        {
            "id": "market",
            "name": "市场风险",
            "name_en": "Market Risk",
            "metrics": [
                _metric("interval_return", "区间收益率", value=core_pack.get("interval_return_pct"), unit="%", group="核心风险指标", note="核心风险指标"),
                _metric("day_return", "涨跌幅（日）", value=_round(day_return, 3), unit="%", group="核心风险指标"),
                _metric("annualized_vol", "年化波动率", value=core_pack.get("annualized_volatility_pct"), unit="%", group="核心风险指标", note="核心风险指标"),
                _metric("max_drawdown", "最大回撤", value=core_pack.get("max_drawdown_pct"), unit="%", group="核心风险指标", note="核心风险指标"),
                _metric("equity_beta", "组合 Beta", value=(core_pack.get("equity_beta") or {}).get("value"), unit="", group="核心风险指标", note="核心风险指标 / 业绩归因明细"),
                _metric("sharpe", "夏普比率", value=_round(sharpe, 3), unit="", group="核心风险指标"),
                _metric("info_ratio", "信息比率", value=_round(info_ratio, 3), unit="", group="核心风险指标", status="computed" if info_ratio is not None else "unavailable", note=bench_note),
                _metric("tracking_error", "跟踪误差（年化）", value=_round(tracking_error, 3), unit="%", group="核心风险指标", status="computed" if tracking_error is not None else "unavailable", note=bench_note),
                _metric("rolling_vol_latest", "滚动波动率（最新）", value=_round(rolling_latest, 3), unit="%", group="核心风险指标", note="滚动窗口年化"),
                _metric("daily_var_pct", "日度VaR", value=_round(daily_var_pct, 3), unit="%", group="核心风险指标", note=f"历史模拟 {confidence:.0%}"),
                _metric("turnover", "股票年化换手率", value=_round((core_pack.get("equity_turnover") or {}).get("annualized_turnover_pct"), 2), unit="%", group="交易行为", note="核心风险指标"),
                _metric("duration", "组合久期", value=_round(duration, 3), unit="年", group="利率信用", note="利率信用"),
                _metric("modified_duration", "修正久期（代理）", value=_round(duration, 3), unit="年", group="利率信用"),
                _metric("convexity", "凸性", value=_round(convexity, 3), unit="", group="利率信用", status="computed" if convexity is not None else "unavailable"),
                _metric("dv01", "DV01", value=_round(dv01.get("duration_proxy") if isinstance(dv01, dict) else dv01, 0), unit="", group="利率信用", note="利率信用"),
                _metric("avg_remaining", "平均剩余期限", value=_round(avg_remaining, 3), unit="年", group="利率信用"),
                _metric("credit_spread", "信用利差", value=_round(credit_spread, 3), unit="%", group="利率信用", note="mktdata_fi_credit" if _ext(info, "credit_spread") is not None else "加权YTM−2%"),
                _metric("style_deviation", "投资风格偏离（成长−价值）", value=_round(style_deviation, 2), unit="pct", group="权益与风格", status="computed" if style_deviation is not None else "unavailable", detail=style_detail, note="mktdata_equity_style"),
                _metric("avg_pe", "平均市盈率 PE", value=_round(avg_pe, 1), unit="", group="权益与风格", status="computed" if avg_pe is not None else "unavailable", note="mktdata_quotes"),
                _metric("avg_pb", "平均市净率 PB", value=_round(avg_pb, 1), unit="", group="权益与风格", status="computed" if avg_pb is not None else "unavailable", note="mktdata_quotes"),
                _metric("factor_equity_exposure", "因子敞口·EQUITY", value=_round((factor.get("EQUITY") or {}).get("pct_nav"), 2), unit="%", group="因子敞口", note="RiskEngine Factor Exposure"),
                _metric("factor_rate_credit_exposure", "因子敞口·RATE_CREDIT", value=_round((factor.get("RATE_CREDIT") or {}).get("pct_nav"), 2), unit="%", group="因子敞口", note="RiskEngine Factor Exposure"),
                _metric("factor_fx_exposure", "因子敞口·FX", value=_round((factor.get("FX") or {}).get("pct_nav"), 2), unit="%", group="因子敞口", note="RiskEngine Factor Exposure"),
                _metric("factor_beta", "因子 Beta", value=_round(factor_beta, 3), unit="", group="因子敞口", note="RiskEngine Beta"),
                _metric("factor_tracking_error", "Tracking Error", value=_round(te_engine, 3), unit="%", group="因子敞口", status="computed" if te_engine is not None else "unavailable", note="RiskEngine TE"),
                _metric("fx_exposure", "汇率风险敞口占比", value=_round(fx_mv / nav * 100.0, 2), unit="%", group="汇率与地域", note="非本位币资产"),
                _metric("non_cny_pct", "境外非人民币资产占比", value=_round(non_cny_mv / nav * 100.0, 2), unit="%", group="汇率与地域"),
                _metric("country_conc", "国家/地区集中度", value=_round(country_top, 2), unit="%", group="汇率与地域", detail=country_detail),
            ],
        },
        {
            "id": "credit",
            "name": "信用风险",
            "name_en": "Credit Risk",
            "metrics": [
                _metric("issuer_rating_dist", "主体评级档位数", value=len(issuer_dist) or None, unit="档", group="评级与个券", status="computed" if bonds else "unavailable", note="issuer_rating", detail=", ".join(f"{r['rating']}:{_round(r['weight_pct'], 1)}%" for r in issuer_dist) or None),
                _metric("debt_rating_dist", "债项评级档位数", value=len(debt_dist) or None, unit="档", group="评级与个券", status="computed" if bonds else "unavailable", note="debt_rating", detail=", ".join(f"{r['rating']}:{_round(r['weight_pct'], 1)}%" for r in debt_dist) or None),
                _metric("issuer_ig_pct", "主体评级·投资级占比", value=_round(_ig_pct(issuer_dist), 2), unit="%", group="评级与个券", note="BBB-及以上 · 占债券市值"),
                _metric("issuer_below_ig_pct", "主体评级·低于投资级占比", value=_round(None if not issuer_dist else 100.0 - (_ig_pct(issuer_dist) or 0.0), 2), unit="%", group="评级与个券", note="含 NR"),
                _metric("debt_ig_pct", "债项评级·投资级占比", value=_round(_ig_pct(debt_dist), 2), unit="%", group="评级与个券"),
                _metric("debt_below_ig_pct", "债项评级·低于投资级占比", value=_round(None if not debt_dist else 100.0 - (_ig_pct(debt_dist) or 0.0), 2), unit="%", group="评级与个券"),
                _metric("issuer_hhi", "发行人集中度 HHI", value=_round(issuer_hhi, 1), unit="", group="集中度"),
                _metric("top_issuer_pct", "最大发行人占比", value=_round(top_issuer, 2), unit="%", group="集中度"),
                _metric("bond_top5", "前五大个券集中度", value=_round(_top_pct(bonds, nav, 5), 2), unit="%", group="集中度"),
                _metric("bond_top10", "前十大个券集中度", value=_round(_top_pct(bonds, nav, 10), 2), unit="%", group="集中度"),
                _metric("controller_conc", "同一实际控制人集中度", value=_round(ctrl_pct, 2), unit="%", group="集中度", detail=str(ctrl_name) if ctrl_name else None, note="机构集团穿透"),
                _metric("cs01", "CS01", value=_round(cs01.get("duration_proxy") if isinstance(cs01, dict) else cs01, 0), unit="", group="利差敏感", note="利率信用"),
                _metric("implied_pd", "隐含违约率", value=_round(implied_pd, 4), unit="%", group="利差敏感", status="computed" if implied_pd is not None else "unavailable", note="mktdata_fi_credit"),
                _metric("neg_news", "负面舆情条数", value=int(neg_news) if neg_news is not None else 0, unit="条", group="舆情", note="mktdata_issuer_news"),
            ],
        },
        {
            "id": "liquidity",
            "name": "流动性风险",
            "name_en": "Liquidity Risk",
            "metrics": [
                _metric("ttl_10", "变现天数 TTL 10%", value=_round(ttl.get("ttl_10"), 1), unit="天", group="变现天数", note="流动性压测"),
                _metric("ttl_25", "变现天数 TTL 25%", value=_round(ttl.get("ttl_25"), 1), unit="天", group="变现天数", note="流动性压测"),
                _metric("ttl_50", "变现天数 TTL 50%", value=_round(ttl.get("ttl_50"), 1), unit="天", group="变现天数", note="流动性压测"),
                _metric("avg_ttl", "平均变现天数", value=_round(ttl.get("avg_ttl"), 1), unit="天", group="变现天数"),
                _metric("stock_ttl", "股票变现天数", value=_round(ttl.get("stock_ttl"), 1), unit="天", group="变现天数", status="computed" if ttl.get("stock_ttl") is not None else "unavailable"),
                _metric("bond_ttl", "债券变现天数", value=_round(ttl.get("bond_ttl"), 1), unit="天", group="变现天数"),
                _metric("over_10d", "变现超10天资产占比", value=_round(ttl.get("over_10d_pct"), 2), unit="%", group="变现天数"),
                _metric("over_40d", "变现超40天资产占比", value=_round(ttl.get("over_40d_pct"), 2), unit="%", group="变现天数"),
                _metric("cash_pct", "现金及高流动性资产占比", value=_round(high_liq_pct, 2), unit="%", group="流动性结构"),
                _metric("cash_only", "现金及存款占比", value=_round(cash_mv / nav * 100.0, 2), unit="%", group="流动性结构"),
                _metric("rate_bond_pct", "国债/利率债占比", value=_round(rate_bond_pct, 2), unit="%", group="流动性结构"),
                _metric("restricted_pct", "流动受限资产占比", value=_round(restricted_pct, 2), unit="%", group="流动性结构", note="停牌或不可卖出股票"),
                _metric("lcr_15", "高流动性资产覆盖率（赎回15%）", value=_round(lcr_15, 2), unit="x", group="覆盖率与申赎", note="流动性压测"),
                _metric("net_redemption", "净赎回占期初净值", value=_round(net_redemption, 2), unit="%", group="覆盖率与申赎", status="computed" if net_redemption is not None else "unavailable", note="transact_portfolio_cashflow"),
                _metric("investor_conc", "前十大投资者集中度", value=_round(investor_top10, 2), unit="%", group="覆盖率与申赎", status="computed" if investor_top10 is not None else "unavailable", detail=investor_detail, note="para_sponsor + holder_rank"),
            ],
        },
        {
            "id": "concentration",
            "name": "集中度与杠杆",
            "name_en": "Concentration & Leverage",
            "metrics": [
                _metric("equity_top5", "前五大重仓股占比", value=_round(_top_pct(equities, nav, 5), 2), unit="%", group="股票集中"),
                _metric("equity_top10", "前十大重仓股占比", value=_round(_top_pct(equities, nav, 10), 2), unit="%", group="股票集中"),
                _metric("equity_largest", "最大个股占比", value=_round(_top_pct(equities, nav, 1), 2), unit="%", group="股票集中"),
                _metric("equity_hhi", "个股集中度 HHI", value=_round(equity_hhi, 1), unit="", group="股票集中"),
                _metric("sector_hhi", "行业集中度 HHI", value=_round(sector_hhi, 1), unit="", group="股票集中", note="因子行为"),
                _metric("equity_float", "最大个股占流通股", value=_round(equity_float, 4), unit="%", group="股票集中", status="computed" if equity_float is not None else "unavailable", detail=f"占总股本 {equity_of_shares}%" if equity_of_shares is not None else None, note="mktdata_stock_static"),
                _metric("bond_conc_top10", "前十大重仓债占比", value=_round(_top_pct(bonds, nav, 10), 2), unit="%", group="债券集中"),
                _metric("issuer_top", "最大发行人占比（债）", value=_round(top_issuer, 2), unit="%", group="债券集中"),
                _metric("controller_eq", "同一实际控制人集中度", value=_round(ctrl_pct, 2), unit="%", group="债券集中", detail=str(ctrl_name) if ctrl_name else None),
                _metric("country_qdii", "国家/地区集中度", value=_round(country_top, 2), unit="%", group="地域与杠杆", detail=country_detail),
                _metric("leverage", "杠杆倍数（资产/净值）", value=_round(leverage, 3), unit="x", group="地域与杠杆"),
                _metric("repo_pct", "正回购负债占比", value=_round(repo_mv / nav * 100.0, 2), unit="%", group="地域与杠杆"),
            ],
        },
        {
            "id": "compliance",
            "name": "投资合规与操作风险",
            "name_en": "Compliance & Operational Risk",
            "metrics": [
                _ams_metric("ams_wam", "WAM 加权平均届满期", wam_days, limit=60, op="<=", unit="天", ams_code="2.2", hard=True, applicable=is_mmf),
                _ams_metric("ams_wal", "WAL 加权平均有效期／寿命", wal_days, limit=120, op="<=", unit="天", ams_code="2.4", hard=True, applicable=is_mmf),
                _ams_metric("ams_wla", "WLA 每周流动资产", wla_pct, limit=15.0, op=">=", unit="%", ams_code="2.6", hard=True, applicable=is_mmf or wla_pct is not None),
                _ams_metric("ams_wam_internal", "WAM（内部从严）", wam_days, limit=wam_internal_limit, op="<=", unit="天", ams_code="3.29", hard=False, scheme="BAMUSDMMF风控002", applicable=is_mmf),
                _ams_metric("ams_wal_internal", "WAL（内部从严）", wal_days, limit=wal_internal_limit, op="<=", unit="天", ams_code="3.30", hard=False, scheme="BAMUSDMMF风控002", applicable=is_mmf),
                _ams_metric("ams_wla_internal", "WLA（内部从严）", wla_pct, limit=wla_internal_limit, op=">=", unit="%", ams_code="3.32", hard=False, scheme="BAMUSDMMF风控002", applicable=is_mmf or wla_pct is not None),
                _ams_metric("ams_single_issuer", "单一主体：工具 + 存款", top_issuer, limit=10.0, op="<=", unit="%", ams_code="2.3", hard=True, applicable=top_issuer is not None),
                _metric("process_exceptions", "流程异常节点数", value=process_exceptions, unit="个", group="操作与限额", status="computed" if process_exceptions is not None else "unavailable", note="待处理审核请求"),
                _metric("counterparty_limit_usage", "交易对手限额使用率", value=_round(cpty_usage, 1), unit="%", group="操作与限额", status="computed" if cpty_usage is not None else "unavailable", note="回购本金 / 授信额度"),
                _metric("regulatory_redlines", "监管红线触发数", value=redlines, unit="条", group="操作与限额", status="computed" if redlines is not None else "unavailable", note="单一发行人超监管上限等"),
                _metric("related_party_pct", "关联交易持仓占比", value=_round(related_party, 2), unit="%", group="操作与限额", status="computed" if related_party is not None else "unavailable", note="para_port_related_party"),
                _metric("deposit_bank_usage", "存款行额度使用率", value=_round(deposit_usage, 1), unit="%", group="操作与限额", status="computed" if deposit_usage is not None else "unavailable", note="合规 · AMS 额度 · 额度管理-额度设置 · 硬指标 · 限额 <=100.0%"),
            ],
        },
        {
            "id": "stress",
            "name": "产品压力测试",
            "name_en": "Stress Testing",
            "metrics": [
                _metric("rate_shock_50", "利率+50BP 偏离金额", value=_round(rate_shock_pnl, 0), unit="", group="利率冲击", note="流动性压测"),
                _metric("rate_shock_50_pct", "利率+50BP 偏离占比", value=rate_impact, unit="%", group="利率冲击"),
                _metric("redemption_15_lcr", "极端赎回15%·高流动性覆盖率", value=_round(lcr_15, 2), unit="x", group="赎回冲击", note="流动性压测（赎回15%）"),
                _metric("redemption_20_lcr", "赎回20%·高流动性覆盖率", value=_round(lcr_20, 2), unit="x", group="赎回冲击"),
                _metric("market_crash_nav", "股指极端下跌·净值跌幅代理（β×-20%）", value=market_crash, unit="%", group="市场冲击", status="computed" if market_crash is not None else "unavailable", note=bench_note),
                _metric("credit_default_3", "信用违约3%·净值损失预测", value=credit_default, unit="%", group="信用冲击"),
                _metric("top5_investor_redeem", "前五大投资者全部赎回覆盖率", value=_round(top5_cover, 2), unit="x", group="赎回冲击", status="computed" if top5_cover is not None else "unavailable", note="7日可变现 / 前五大持仓金额"),
            ],
        },
    ]

    computed = sum(1 for c in categories for m in c["metrics"] if m["status"] == "computed")
    derived = sum(1 for c in categories for m in c["metrics"] if m["status"] == "derived")
    unavailable = sum(1 for c in categories for m in c["metrics"] if m["status"] == "unavailable")

    return {
        "module": "metric_board",
        "fund_id": str(snapshot.fund_id),
        "period_start": core_pack.get("period_start"),
        "period_end": core_pack.get("period_end"),
        "data_as_of": snapshot.as_of_date.isoformat(),
        "benchmark_id": (core_pack.get("equity_beta") or {}).get("benchmark_id") or bench_id,
        "source": "riskengine",
        "summary": {
            "computed": computed,
            "derived": derived,
            "unavailable": unavailable,
            "total": computed + derived + unavailable,
        },
        "categories": categories,
        "category_ids": [c[0] for c in RISK_CATEGORIES],
        "required_metric_ids": {key: list(ids) for key, ids in REQUIRED_METRIC_IDS.items()},
        "credit_rating_detail": {
            "as_of_date": snapshot.as_of_date.isoformat(),
            "total_bond_market_value": bond_mv,
            "bond_count": len(bonds),
            "issuer_rating_distribution": issuer_dist,
            "debt_rating_distribution": debt_dist,
            "issuer_investment_grade_pct": _ig_pct(issuer_dist),
            "issuer_below_investment_grade_pct": None
            if not issuer_dist
            else 100.0 - (_ig_pct(issuer_dist) or 0.0),
            "debt_investment_grade_pct": _ig_pct(debt_dist),
            "debt_below_investment_grade_pct": None if not debt_dist else 100.0 - (_ig_pct(debt_dist) or 0.0),
        },
        "confidence": confidence,
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    confidence: float = 0.99,
    horizon_days: int = 1,
    rolling_window: int = 20,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict[str, Any]:
    """风险指标 Tab 四大业务模块打包。"""

    core = module_core_profile(
        bound, meta=meta, period_start=period_start, period_end=period_end
    )
    rolling = module_rolling_volatility(
        bound, window=rolling_window, period_start=period_start, period_end=period_end
    )
    var_cmp = module_var_compare(bound, confidence=confidence, horizon_days=horizon_days)
    board = module_metric_board(bound, meta=meta, core=core, confidence=confidence)
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/investment-risk/indicators#risk-exposure",
        "tab": "core",
        "fund_id": str(bound.snapshot.fund_id),
        "as_of_date": bound.snapshot.as_of_date.isoformat(),
        "business_modules": list(BUSINESS_MODULES),
        "risk_categories": [
            {"id": cid, "name": name, "name_en": name_en} for cid, name, name_en in RISK_CATEGORIES
        ],
        "modules": {
            "core_profile": core,
            "rolling_volatility": rolling,
            "var_compare": var_cmp,
            "metric_board": board,
        },
        # HTTP 同形摘要，便于对账
        "indicators": {
            "interval_return_pct": core["interval_return_pct"],
            "annualized_volatility_pct": core["annualized_volatility_pct"],
            "max_drawdown_pct": core["max_drawdown_pct"],
            "max_drawdown_start": core["max_drawdown_start"],
            "max_drawdown_end": core["max_drawdown_end"],
            "sample_size": core["sample_size"],
            "equity_turnover": core["equity_turnover"],
            "equity_beta": core["equity_beta"],
        },
        "var_compare": {
            "confidence": var_cmp["confidence"],
            "horizon_days": var_cmp["horizon_days"],
            "max_var_pct_nav": var_cmp["max_var_pct_nav"],
            "results": var_cmp["results"],
        },
        "timeseries": rolling["points"],
        "categories": board["categories"],
        "credit_rating_detail": board["credit_rating_detail"],
        "summary": board["summary"],
        "adapters": bound.engine.adapters_status(),
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    core = modules.get("core_profile") or {}
    if core.get("sample_size", 0) >= 2:
        if core.get("annualized_volatility_pct") is None:
            errors.append("core_profile.annualized_volatility_pct")
        if core.get("max_drawdown_pct") is None:
            errors.append("core_profile.max_drawdown_pct")
    rolling = modules.get("rolling_volatility") or {}
    if core.get("sample_size", 0) >= 2 and not rolling.get("points"):
        errors.append("rolling_volatility.points")
    var_cmp = modules.get("var_compare") or {}
    methods = {row.get("method_requested") for row in (var_cmp.get("results") or [])}
    for required in ("historical", "monte_carlo", "distribution"):
        if required not in methods:
            errors.append(f"var_compare.{required}")
    board = modules.get("metric_board") or {}
    cat_ids = {c.get("id") for c in (board.get("categories") or [])}
    for cid, _, _ in RISK_CATEGORIES:
        if cid not in cat_ids:
            errors.append(f"metric_board.{cid}")
            continue
        cat = next(c for c in board["categories"] if c["id"] == cid)
        if not cat.get("metrics"):
            errors.append(f"metric_board.{cid}.metrics")
        present = {m.get("id") for m in (cat.get("metrics") or [])}
        for metric_id in REQUIRED_METRIC_IDS.get(cid, ()):
            if metric_id not in present:
                errors.append(f"metric_board.{cid}.{metric_id}")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "risk_categories": [c[0] for c in RISK_CATEGORIES],
        "required_metric_ids": {key: list(ids) for key, ids in REQUIRED_METRIC_IDS.items()},
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
