"""Riskfolio-backed portfolio construction. Vendor import stays in this adapter."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

OPTIMIZATION_METHODS = (
    "construction",
    "saa",
    "taa",
    "risk_budget",
    "risk_parity",
    "black_litterman",
    "hrp",
    "herc",
    "cvar",
)

DEFAULT_CONSTRAINTS: dict[str, Any] = {
    "min_weight": 0.0,
    "max_weight": 1.0,
    "max_name_weight": 1.0,
    "long_only": True,
    "min_liquidity_pct": 0.0,
    "max_turnover": 1.0,
    "cash_asset": "CASH",
}


def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
    total = float(sum(weights.values()))
    if total <= 0:
        n = len(weights)
        return {str(k): 1.0 / n for k in weights} if n else {}
    return {str(k): float(v) / total for k, v in weights.items()}


def apply_constraints(
    weights: Mapping[str, float],
    constraints: Mapping[str, Any] | None = None,
    *,
    current_weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Clip, liquidity-floor, turnover-cap and renormalize."""

    cfg = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    lo = float(cfg["min_weight"])
    hi = min(float(cfg["max_weight"]), float(cfg["max_name_weight"]))
    if cfg.get("long_only", True):
        lo = max(lo, 0.0)
    assets = list(weights)
    clipped = {a: min(max(float(weights[a]), lo), hi) for a in assets}
    for _ in range(25):
        clipped = _normalize(clipped)
        clipped = {a: min(max(clipped[a], lo), hi) for a in assets}
        if abs(sum(clipped.values()) - 1.0) < 1e-9 and all(
            lo - 1e-12 <= clipped[a] <= hi + 1e-12 for a in assets
        ):
            break
    # Final normalize can push a clipped weight above ``hi`` by float noise;
    # re-clip once and absorb the residual into the largest under-cap name.
    if abs(sum(clipped.values()) - 1.0) >= 1e-12:
        clipped = _normalize(clipped)
        clipped = {a: min(max(clipped[a], lo), hi) for a in assets}
        residual = 1.0 - sum(clipped.values())
        if abs(residual) > 1e-12:
            room = sorted(
                ((a, hi - clipped[a]) for a in assets if hi - clipped[a] > 1e-15),
                key=lambda item: item[1],
                reverse=True,
            )
            for asset, capacity in room:
                take = min(capacity, residual) if residual > 0 else max(-clipped[asset] + lo, residual)
                clipped[asset] += take
                residual -= take
                if abs(residual) <= 1e-12:
                    break
    clipped = {a: min(max(float(clipped[a]), lo), hi) for a in assets}

    cash = str(cfg.get("cash_asset") or "CASH")
    min_liq = float(cfg.get("min_liquidity_pct") or 0.0)
    if min_liq > 0 and cash in clipped and clipped[cash] < min_liq:
        need = min_liq - clipped[cash]
        donors = sorted((a for a in assets if a != cash), key=lambda a: clipped[a], reverse=True)
        for donor in donors:
            take = min(need, max(clipped[donor] - lo, 0.0))
            clipped[donor] -= take
            clipped[cash] += take
            need -= take
            if need <= 1e-12:
                break
        clipped = _normalize(clipped)

    if current_weights:
        turned = turnover(clipped, current_weights)
        cap = float(cfg.get("max_turnover") or 1.0)
        if turned > cap + 1e-12 and turned > 0:
            alpha = cap / turned
            keys = set(clipped) | set(current_weights)
            clipped = {
                k: (1.0 - alpha) * float(current_weights.get(k, 0.0)) + alpha * float(clipped.get(k, 0.0))
                for k in keys
            }
            clipped = _normalize(clipped)
    return clipped


def turnover(new_weights: Mapping[str, float], old_weights: Mapping[str, float]) -> float:
    keys = set(new_weights) | set(old_weights)
    return 0.5 * sum(abs(float(new_weights.get(k, 0.0)) - float(old_weights.get(k, 0.0))) for k in keys)


def covariance_risk_contribution(
    weights: Mapping[str, float],
    returns: pd.DataFrame,
) -> dict[str, float]:
    assets = list(returns.columns)
    w = np.array([float(weights.get(a, 0.0)) for a in assets], dtype=float)
    cov = returns.cov().to_numpy()
    port_var = float(w @ cov @ w)
    if port_var <= 0:
        n = max(len(assets), 1)
        return {a: 1.0 / n for a in assets}
    mrc = cov @ w
    rc = w * mrc
    total = float(rc.sum())
    if abs(total) < 1e-18:
        n = max(len(assets), 1)
        return {a: 1.0 / n for a in assets}
    return {a: float(rc[i] / total) for i, a in enumerate(assets)}


def _equal_weights(assets: list[str]) -> dict[str, float]:
    n = max(len(assets), 1)
    return {a: 1.0 / n for a in assets}


def _inverse_vol_weights(returns: pd.DataFrame) -> dict[str, float]:
    vol = returns.std(ddof=1).replace(0.0, np.nan)
    inv = (1.0 / vol).fillna(0.0)
    return _normalize({a: float(inv[a]) for a in returns.columns})


def _risk_parity_weights(
    returns: pd.DataFrame,
    budgets: Mapping[str, float] | None = None,
) -> dict[str, float]:
    assets = list(returns.columns)
    cov = returns.cov().to_numpy()
    n = len(assets)
    if n == 0:
        return {}
    if n == 1:
        return {assets[0]: 1.0}
    if budgets:
        b = np.array([float(budgets.get(a, 0.0)) for a in assets], dtype=float)
        if b.sum() <= 0:
            b = np.ones(n)
        b = b / b.sum()
    else:
        b = np.ones(n) / n
    w = b.copy()
    for _ in range(250):
        port_var = float(w @ cov @ w)
        if port_var <= 0:
            break
        rc = w * (cov @ w)
        rc_sum = float(rc.sum())
        if abs(rc_sum) < 1e-18:
            break
        share = rc / rc_sum
        w = w * np.sqrt(b / np.clip(share, 1e-12, None))
        w = np.clip(w, 0.0, None)
        total = float(w.sum())
        if total <= 0:
            w = b.copy()
            break
        w = w / total
        if float(np.max(np.abs(share - b))) < 1e-7:
            break
    return {a: float(w[i]) for i, a in enumerate(assets)}


def _quasi_diag(link: np.ndarray) -> list[int]:
    root = to_tree(link)
    order: list[int] = []

    def _recurse(node) -> None:
        if node.is_leaf():
            order.append(node.id)
        else:
            _recurse(node.left)
            _recurse(node.right)

    _recurse(root)
    return order


def _cluster_var(cov: pd.DataFrame, items: list[str]) -> float:
    sub = cov.loc[items, items].to_numpy()
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)


def _hrp_weights(returns: pd.DataFrame) -> dict[str, float]:
    cov = returns.cov()
    corr = returns.corr()
    assets = list(corr.columns)
    if len(assets) <= 1:
        return {assets[0]: 1.0} if assets else {}
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
            var_left, var_right = _cluster_var(cov, left), _cluster_var(cov, right)
            alpha = 1.0 - var_left / (var_left + var_right)
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha
    return {a: float(weights[a]) for a in assets}


def _herc_weights(returns: pd.DataFrame) -> dict[str, float]:
    """Hierarchical Equal Risk Contribution: equal cluster split + inverse-vol within."""

    cov = returns.cov()
    corr = returns.corr()
    assets = list(corr.columns)
    if len(assets) <= 1:
        return {assets[0]: 1.0} if assets else {}
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
            weights[left] *= 0.5
            weights[right] *= 0.5
    vol = np.sqrt(np.clip(np.diag(cov.loc[assets, assets].to_numpy()), 1e-18, None))
    inv = 1.0 / vol
    scale = {a: float(inv[i]) for i, a in enumerate(assets)}
    # Re-weight within original equal-cluster masses by inverse vol, then normalize.
    mixed = {a: float(weights[a]) * scale[a] for a in assets}
    return _normalize(mixed)


def _cvar_weights(returns: pd.DataFrame, confidence: float = 0.95) -> dict[str, float]:
    assets = list(returns.columns)
    n = len(assets)
    if n == 0:
        return {}
    if n == 1:
        return {assets[0]: 1.0}
    sample = returns.to_numpy(dtype=float)
    alpha_pct = (1.0 - confidence) * 100.0

    def objective(w: np.ndarray) -> float:
        port = sample @ w
        hurdle = float(np.percentile(port, alpha_pct))
        tail = port[port <= hurdle]
        if tail.size == 0:
            return -hurdle
        return -float(np.mean(tail))

    bounds = [(0.0, 1.0)] * n
    cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    seed = np.ones(n) / n
    result = minimize(objective, seed, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 200})
    if not result.success:
        # Worse (more negative) asset CVaR gets less weight.
        asset_cvar = []
        for col in assets:
            series = returns[col].to_numpy()
            hurdle = float(np.percentile(series, alpha_pct))
            tail = series[series <= hurdle]
            asset_cvar.append(float(np.mean(tail)) if tail.size else hurdle)
        scores = np.array([max(c, 1e-8) if c > 0 else 1.0 / max(-c, 1e-8) for c in asset_cvar])
        w = scores / scores.sum()
        return {a: float(w[i]) for i, a in enumerate(assets)}
    w = np.clip(result.x, 0.0, None)
    w = w / w.sum()
    return {a: float(w[i]) for i, a in enumerate(assets)}


def _black_litterman_weights(
    returns: pd.DataFrame,
    views: Mapping[str, float] | None = None,
) -> dict[str, float]:
    from importlib import import_module

    optimizer = import_module("2_processing.tools.performance.portfolio_optimizer")
    prices = (1.0 + returns).cumprod()
    manager = optimizer.PortfolioManager(list(returns.columns), weight_bounds=(0.0, 1.0))
    manager.set_price_panel(prices)
    manager.set_return_model("black_litterman", views=dict(views or {}))
    weights, _metrics = manager.build_portfolio_by_profile("conservative")
    return _normalize(weights)


def _min_vol_weights(returns: pd.DataFrame) -> dict[str, float]:
    from importlib import import_module

    optimizer = import_module("2_processing.tools.performance.portfolio_optimizer")
    prices = (1.0 + returns).cumprod()
    manager = optimizer.PortfolioManager(list(returns.columns), weight_bounds=(0.0, 1.0))
    manager.set_price_panel(prices)
    manager.set_return_model("historical_mean")
    weights, _metrics = manager.build_portfolio_by_profile("conservative")
    return _normalize(weights)


def fallback_optimize(
    returns: pd.DataFrame,
    method: str,
    *,
    constraints: Mapping[str, Any] | None = None,
    current_weights: Mapping[str, float] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    confidence: float = 0.95,
) -> dict[str, float]:
    key = method.strip().lower()
    if key not in OPTIMIZATION_METHODS:
        raise ValueError(f"Unsupported optimization method: {method}")
    if key == "construction":
        raw = _equal_weights(list(returns.columns))
    elif key == "saa":
        raw = _min_vol_weights(returns)
    elif key == "taa":
        raw = _black_litterman_weights(returns, views)
    elif key == "risk_budget":
        raw = _risk_parity_weights(returns, risk_budgets)
    elif key == "risk_parity":
        raw = _risk_parity_weights(returns, None)
    elif key == "black_litterman":
        raw = _black_litterman_weights(returns, views)
    elif key == "hrp":
        raw = _hrp_weights(returns)
    elif key == "herc":
        raw = _herc_weights(returns)
    else:
        raw = _cvar_weights(returns, confidence=confidence)
    return apply_constraints(raw, constraints, current_weights=current_weights)


def try_riskfolio_optimize(
    module: Any,
    returns: pd.DataFrame,
    method: str,
    *,
    constraints: Mapping[str, Any] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
) -> dict[str, float] | None:
    """Best-effort Riskfolio-Lib call. None means caller should use the fallback."""

    if module is None:
        return None
    key = method.strip().lower()
    port = module.Portfolio(returns=returns)
    if hasattr(port, "assets_stats"):
        port.assets_stats(method_mu="hist", method_cov="hist")
    cfg = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    if hasattr(port, "lowerret") is False and hasattr(port, "wmin"):
        port.wmin = float(cfg["min_weight"])
        port.wmax = float(cfg["max_weight"])
    weights = None
    if key in {"risk_parity", "risk_budget"} and hasattr(port, "rp_optimization"):
        extra: dict[str, Any] = {}
        if key == "risk_budget" and risk_budgets and hasattr(port, "b"):
            port.b = pd.Series({a: float(risk_budgets.get(a, 0.0)) for a in returns.columns})
        weights = port.rp_optimization(model="Classic", rm="MV", **extra)
    elif key in {"hrp", "herc"} and hasattr(port, "optimization"):
        model = "HRP" if key == "hrp" else "HERC"
        weights = port.optimization(model=model, rm="MV", obj="MinRisk")
    elif key == "cvar" and hasattr(port, "optimization"):
        weights = port.optimization(model="Classic", rm="CVaR", obj="MinRisk")
    elif key in {"saa", "construction"} and hasattr(port, "optimization"):
        weights = port.optimization(model="Classic", rm="MV", obj="MinRisk")
    elif key in {"taa", "black_litterman"} and views and hasattr(module, "BlackLitterman"):
        return None
    if weights is None:
        return None
    if hasattr(weights, "to_dict"):
        series = weights.squeeze() if hasattr(weights, "squeeze") else weights
        raw = {str(k): float(v) for k, v in series.to_dict().items()}
    elif isinstance(weights, dict):
        raw = {str(k): float(v) for k, v in weights.items()}
    else:
        return None
    return apply_constraints(raw, constraints)
