"""组合配置与优化纯计算核（无 DB、不 import 2_processing）。

收益模型 / 个股指标 / 有效前沿 / 画像权重 / HRP / 相关性，全部在本模块完成。
闸门优化走 Riskfolio 适配器（``RiskEngine().riskfolio``）。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

TRADING_DAYS = 252
PROFILE_NAMES = ("conservative", "balanced", "aggressive", "hrp")


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = float(sum(weights.values()))
    if total <= 0:
        n = len(weights)
        return {str(k): 1.0 / n for k in weights} if n else {}
    return {str(k): float(v) / total for k, v in weights.items()}


def prices_from_returns(returns: pd.DataFrame, start: float = 100.0) -> pd.DataFrame:
    return start * (1.0 + returns).cumprod()


def ensure_panel(
    *,
    prices: pd.DataFrame | None = None,
    returns: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if prices is not None and not prices.empty:
        px = prices.astype(float).dropna(how="any")
        rets = px.pct_change().dropna()
        return px, rets
    if returns is None or returns.empty:
        raise ValueError("prices or returns required")
    rets = returns.astype(float).dropna(how="any")
    return prices_from_returns(rets), rets


def sample_cov(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.cov() * TRADING_DAYS


def historical_mean(returns: pd.DataFrame) -> pd.Series:
    return returns.mean() * TRADING_DAYS


def real_cagr(prices: pd.DataFrame) -> pd.Series:
    n = max(len(prices) - 1, 1)
    total = prices.iloc[-1] / prices.iloc[0] - 1.0
    years = n / TRADING_DAYS
    if years <= 0:
        return pd.Series(0.0, index=prices.columns)
    return (1.0 + total).pow(1.0 / years) - 1.0


def capm_return(returns: pd.DataFrame, risk_free_rate: float) -> pd.Series:
    market = returns.mean(axis=1)
    var_m = float(market.var())
    if var_m <= 0:
        return historical_mean(returns)
    excess_m = float(market.mean() * TRADING_DAYS - risk_free_rate)
    out = {}
    for col in returns.columns:
        cov = float(np.cov(returns[col], market, ddof=1)[0, 1])
        beta = cov / var_m
        out[col] = risk_free_rate + beta * excess_m
    return pd.Series(out)


def black_litterman_return(
    returns: pd.DataFrame,
    cov_ann: pd.DataFrame,
    risk_free_rate: float,
    *,
    market_caps: Mapping[str, float] | None = None,
    views: Mapping[str, float] | None = None,
) -> pd.Series:
    assets = list(returns.columns)
    mcap = pd.Series({a: float((market_caps or {}).get(a, 1.0)) for a in assets})
    mcap = mcap / mcap.sum()
    sigma = cov_ann.to_numpy(dtype=float)
    # 隐含风险厌恶：δ ≈ (E[rm]-rf)/σ_m²
    market = returns.mean(axis=1)
    er_m = float(market.mean() * TRADING_DAYS)
    var_m = float(market.var() * TRADING_DAYS)
    delta = (er_m - risk_free_rate) / var_m if var_m > 0 else 2.5
    pi = delta * sigma @ mcap.to_numpy()
    prior = pd.Series(pi, index=assets)
    if not views:
        return prior
    clean = {k: float(v) for k, v in views.items() if k in assets}
    if not clean:
        return prior
    # 绝对观点：后验 ≈ (τΣ)^{-1}π + P'Ω^{-1}Q 的简化凸组合
    tau = 0.05
    blended = prior.copy()
    for asset, view in clean.items():
        blended[asset] = (1.0 - tau) * float(prior[asset]) + tau * view
    return blended


def compute_return_models(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    risk_free_rate: float,
    market_caps: Mapping[str, float] | None = None,
    views: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    cov = sample_cov(returns)
    hist = historical_mean(returns)
    cagr = real_cagr(prices)
    capm = capm_return(returns, risk_free_rate)
    bl = black_litterman_return(returns, cov, risk_free_rate, market_caps=market_caps, views=views)
    period = prices.iloc[-1] / prices.iloc[0] - 1.0
    rows = []
    for asset in prices.columns:
        rows.append(
            {
                "asset": str(asset),
                "historical_mean": float(hist[asset]),
                "real_cagr": float(cagr[asset]),
                "capm": float(capm[asset]),
                "black_litterman": float(bl[asset]),
                "period_total_return": float(period[asset]),
            }
        )
    return rows


def select_mu(return_models: Sequence[Mapping[str, Any]], return_model: str) -> pd.Series:
    key = {
        "historical_mean": "historical_mean",
        "real_cagr": "real_cagr",
        "capm": "capm",
        "black_litterman": "black_litterman",
        "backtest": "real_cagr",
    }.get(return_model, "historical_mean")
    return pd.Series({row["asset"]: float(row[key]) for row in return_models})


def asset_metrics(returns: pd.DataFrame, risk_free_rate: float) -> list[dict[str, Any]]:
    rows = []
    for col in returns.columns:
        r = returns[col]
        ann_ret = float(r.mean() * TRADING_DAYS)
        ann_vol = float(r.std(ddof=1) * np.sqrt(TRADING_DAYS))
        sharpe = (ann_ret - risk_free_rate) / ann_vol if ann_vol > 0 else 0.0
        cum = (1.0 + r).cumprod()
        max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
        var95 = float(np.percentile(r, 5))
        tail = r[r <= var95]
        cvar95 = float(tail.mean()) if len(tail) else var95
        rows.append(
            {
                "asset": str(col),
                "expected_return": ann_ret,
                "volatility": ann_vol,
                "sharpe": float(sharpe),
                "max_drawdown": max_dd,
                "var_95": var95,
                "cvar_95": cvar95,
            }
        )
    return rows


def portfolio_metrics(
    weights: Mapping[str, float],
    *,
    mu: pd.Series,
    cov: pd.DataFrame,
    returns: pd.DataFrame,
    risk_free_rate: float,
) -> dict[str, float]:
    cols = list(returns.columns)
    w = np.array([float(weights.get(c, 0.0)) for c in cols], dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(cols)) / max(len(cols), 1)
    else:
        w = w / w.sum()
    port_daily = returns.to_numpy(dtype=float) @ w
    exp_ret = float(mu.reindex(cols).fillna(0.0).to_numpy() @ w)
    vol = float(np.sqrt(max(w @ cov.reindex(index=cols, columns=cols).to_numpy() @ w, 0.0)))
    sharpe = (exp_ret - risk_free_rate) / vol if vol > 0 else 0.0
    cum = np.cumprod(1.0 + port_daily)
    peaks = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum / peaks - 1.0)) if len(cum) else 0.0
    var95 = float(np.percentile(port_daily, 5)) if len(port_daily) else 0.0
    tail = port_daily[port_daily <= var95]
    cvar95 = float(np.mean(tail)) if len(tail) else var95
    return {
        "expected_return": exp_ret,
        "volatility": vol,
        "sharpe": float(sharpe),
        "max_drawdown": max_dd,
        "var_95": var95,
        "cvar_95": cvar95,
    }


def _mv_optimize(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    objective: str,
    risk_free_rate: float = 0.0,
    weight_bounds: tuple[float, float] = (0.0, 1.0),
    risk_aversion: float = 1.0,
    target_return: float | None = None,
) -> dict[str, float]:
    assets = list(mu.index)
    n = len(assets)
    if n == 0:
        return {}
    if n == 1:
        return {assets[0]: 1.0}
    mu_v = mu.to_numpy(dtype=float)
    sigma = cov.reindex(index=assets, columns=assets).to_numpy(dtype=float)
    lo, hi = weight_bounds
    bounds = [(lo, hi)] * n
    cons: list[dict[str, Any]] = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    seed = np.ones(n) / n

    def port_vol(w: np.ndarray) -> float:
        return float(np.sqrt(max(w @ sigma @ w, 0.0)))

    def port_ret(w: np.ndarray) -> float:
        return float(mu_v @ w)

    if objective == "min_vol":
        obj = lambda w: port_vol(w)
    elif objective == "max_sharpe":
        obj = lambda w: -(port_ret(w) - risk_free_rate) / (port_vol(w) + 1e-12)
    elif objective == "max_utility":
        obj = lambda w: -(port_ret(w) - 0.5 * risk_aversion * (port_vol(w) ** 2))
    elif objective == "target_return" and target_return is not None:
        cons.append({"type": "eq", "fun": lambda w, tr=target_return: port_ret(w) - tr})
        obj = lambda w: port_vol(w)
    else:
        obj = lambda w: port_vol(w)

    result = minimize(obj, seed, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 250})
    w = np.clip(result.x if result.success else seed, lo, hi)
    if w.sum() <= 0:
        w = seed
    w = w / w.sum()
    return {assets[i]: float(w[i]) for i in range(n)}


def _quasi_diag(link: np.ndarray) -> list[int]:
    root = to_tree(link)
    order: list[int] = []

    def _recurse(node: Any) -> None:
        if node.is_leaf():
            order.append(node.id)
        else:
            _recurse(node.left)
            _recurse(node.right)

    _recurse(root)
    return order


def hrp_weights(returns: pd.DataFrame) -> dict[str, float]:
    cov = returns.cov()
    corr = returns.corr()
    assets = list(corr.columns)
    if len(assets) == 1:
        return {assets[0]: 1.0}
    dist = np.sqrt(np.clip((1.0 - corr.to_numpy()) / 2.0, 0.0, None))
    link = linkage(squareform(dist, checks=False), method="single")
    ordered = [assets[i] for i in _quasi_diag(link)]
    weights = pd.Series(1.0, index=ordered)
    clusters = [ordered]
    while clusters:
        clusters = [
            c[j:k]
            for c in clusters
            for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
            if len(c) > 1
        ]
        for i in range(0, len(clusters), 2):
            left, right = clusters[i], clusters[i + 1]
            def _var(items: list[str]) -> float:
                sub = cov.loc[items, items].to_numpy()
                ivp = 1.0 / np.diag(sub)
                ivp /= ivp.sum()
                return float(ivp @ sub @ ivp)
            v_left, v_right = _var(left), _var(right)
            alpha = 1.0 - v_left / (v_left + v_right)
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha
    return _normalize(weights.to_dict())


def build_profiles(
    mu: pd.Series,
    cov: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    risk_free_rate: float,
    weight_bounds: tuple[float, float] = (0.0, 1.0),
    target_return: float | None = None,
) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    builders = {
        "conservative": lambda: _mv_optimize(mu, cov, objective="min_vol", weight_bounds=weight_bounds),
        "balanced": lambda: _mv_optimize(
            mu, cov, objective="max_sharpe", risk_free_rate=risk_free_rate, weight_bounds=weight_bounds
        ),
        "aggressive": lambda: _mv_optimize(
            mu, cov, objective="max_utility", risk_aversion=1.0, weight_bounds=weight_bounds
        ),
        "hrp": lambda: hrp_weights(returns),
    }
    for name, builder in builders.items():
        weights = builder()
        metrics = portfolio_metrics(weights, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate)
        profiles[name] = {"weights": weights, "metrics": metrics}
    if target_return is not None:
        weights = _mv_optimize(
            mu,
            cov,
            objective="target_return",
            target_return=target_return,
            weight_bounds=weight_bounds,
        )
        profiles["target_return"] = {
            "weights": weights,
            "metrics": portfolio_metrics(weights, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate),
        }
    return profiles


def efficient_frontier(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    weight_bounds: tuple[float, float] = (0.0, 1.0),
    points: int = 40,
) -> list[dict[str, float]]:
    lo, hi = float(mu.min()), float(mu.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return []
    curve = []
    for target in np.linspace(lo, hi, points):
        try:
            weights = _mv_optimize(
                mu, cov, objective="target_return", target_return=float(target), weight_bounds=weight_bounds
            )
            w = np.array([weights[a] for a in mu.index])
            sigma = cov.reindex(index=mu.index, columns=mu.index).to_numpy()
            vol = float(np.sqrt(max(w @ sigma @ w, 0.0)))
            curve.append({"volatility": vol, "expected_return": float(target)})
        except Exception:
            continue
    return curve


def tangency_point(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    risk_free_rate: float,
    weight_bounds: tuple[float, float] = (0.0, 1.0),
) -> dict[str, float] | None:
    try:
        weights = _mv_optimize(
            mu, cov, objective="max_sharpe", risk_free_rate=risk_free_rate, weight_bounds=weight_bounds
        )
        w = np.array([weights[a] for a in mu.index])
        sigma = cov.reindex(index=mu.index, columns=mu.index).to_numpy()
        vol = float(np.sqrt(max(w @ sigma @ w, 0.0)))
        ret = float(mu.to_numpy() @ w)
        return {"volatility": vol, "expected_return": ret}
    except Exception:
        return None


def correlation_payload(returns: pd.DataFrame) -> dict[str, Any]:
    corr = returns.corr()
    assets = [str(c) for c in corr.columns]
    matrix = [[float(corr.iloc[i, j]) for j in range(len(assets))] for i in range(len(assets))]
    return {"assets": assets, "matrix": matrix}


def check_efficiency(
    weights: Mapping[str, float],
    *,
    mu: pd.Series,
    cov: pd.DataFrame,
    returns: pd.DataFrame,
    risk_free_rate: float,
    weight_bounds: tuple[float, float] = (0.0, 1.0),
) -> dict[str, float | None]:
    current = portfolio_metrics(weights, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate)
    out: dict[str, float | None] = {"alpha_loss": None, "excess_vol": None}
    try:
        eff = _mv_optimize(
            mu,
            cov,
            objective="target_return",
            target_return=current["expected_return"],
            weight_bounds=weight_bounds,
        )
        m = portfolio_metrics(eff, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate)
        out["excess_vol"] = current["volatility"] - m["volatility"]
    except Exception:
        pass
    try:
        # 同波动下的最大收益近似：扫描目标收益
        best_ret = current["expected_return"]
        for target in np.linspace(float(mu.min()), float(mu.max()), 25):
            cand = _mv_optimize(
                mu, cov, objective="target_return", target_return=float(target), weight_bounds=weight_bounds
            )
            m = portfolio_metrics(cand, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate)
            if abs(m["volatility"] - current["volatility"]) <= 0.002 and m["expected_return"] > best_ret:
                best_ret = m["expected_return"]
        out["alpha_loss"] = best_ret - current["expected_return"]
    except Exception:
        pass
    return out
