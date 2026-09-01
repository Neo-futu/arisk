"""ARISK portfolio optimization engine (PyPortfolioOpt + native HRP).

Adapted from scripts/portopt.py for the processing service: pluggable price
source (synthetic / db / yfinance), 4 expected-return models, 6 risk-performance
metrics, multi-profile optimization (min-vol / max-sharpe / max-quadratic-utility /
target-return / HRP), efficient-frontier diagnosis, and matplotlib chart export.

HRP is implemented natively (scipy linkage → quasi-diagonalization → recursive
bisection) because pypfopt 1.6's HRPOpt calls a scipy private attribute removed in
scipy 1.18.
"""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from pypfopt import (
    BlackLittermanModel,
    EfficientFrontier,
    black_litterman,
    expected_returns,
    risk_models,
)
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import squareform

TRADING_DAYS = 252

DEFAULT_UNIVERSE = [
    "GOOG", "AAPL", "META", "AMZN", "AMD",
    "WMT", "BAC", "XOM", "JPM", "PFE",
]


# ── Deterministic synthetic price panel (offline, reproducible) ──
def _seed_for(text: str) -> int:
    return int.from_bytes(hashlib.md5(text.encode()).digest()[:4], "big")


def build_synthetic_prices(universe: list[str], lookback_days: int) -> pd.DataFrame:
    """Reproducible daily price panel with a shared market factor (correlation)
    plus per-asset drift/vol/beta seeded from the ticker name."""
    n = max(lookback_days, 120)
    market_rng = np.random.default_rng(_seed_for("__ARISK_MARKET__"))
    market_ret = market_rng.normal(0.0005, 0.010, size=n)

    cols: dict[str, np.ndarray] = {}
    for ticker in universe:
        rng = np.random.default_rng(_seed_for(ticker))
        drift = rng.uniform(0.0002, 0.0011)        # idiosyncratic drift (~5%-28% p.a.)
        vol = rng.uniform(0.008, 0.028)            # idiosyncratic vol
        beta = rng.uniform(0.5, 1.6)               # market sensitivity
        idio = rng.normal(0.0, vol, size=n)
        daily = drift + beta * market_ret + idio
        start = rng.uniform(20, 500)
        cols[ticker] = start * np.cumprod(1.0 + daily)

    index = pd.bdate_range(end="2026-06-25", periods=n)
    return pd.DataFrame(cols, index=index)


class PortfolioManager:
    """Portfolio analytics & risk engine over a universe of assets."""

    def __init__(
        self,
        tickers: list[str],
        risk_free_rate: float = 0.04,
        weight_bounds: tuple[float, float] = (0.0, 1.0),
    ):
        self.tickers = tickers
        self.risk_free_rate = risk_free_rate
        self.weight_bounds = weight_bounds
        self.prices_df: pd.DataFrame | None = None
        self.returns_df: pd.DataFrame | None = None
        self.mu: pd.Series | None = None
        self.S: pd.DataFrame | None = None

    # ── data ────────────────────────────────────────────────────
    def load_prices(
        self,
        source: str = "synthetic",
        lookback_days: int = 500,
        db_prices: pd.DataFrame | None = None,
        start: "date | None" = None,
        end: "date | None" = None,
    ) -> pd.DataFrame:
        # Explicit start/end define the window; else fall back to lookback_days.
        span_days = lookback_days
        if start and end:
            span_days = max(int((end - start).days * 5 / 7), 60)
        if source == "openbb":
            prices = self._load_openbb(span_days, start, end)
        elif source == "yfinance":
            prices = self._load_yfinance(span_days, start, end)
        elif source == "db" and db_prices is not None and not db_prices.empty:
            prices = db_prices.reindex(columns=self.tickers)
            # Backfill tickers lacking sufficient history with synthetic series.
            missing = [c for c in self.tickers if prices[c].dropna().shape[0] < 60]
            if missing:
                synth = build_synthetic_prices(missing, span_days)
                for c in missing:
                    prices[c] = synth[c].to_numpy()[: len(prices)] if len(prices) else synth[c]
                if not len(prices):
                    prices = build_synthetic_prices(self.tickers, span_days)
            prices = prices.dropna()
        else:
            prices = build_synthetic_prices(self.tickers, span_days)

        self.set_price_panel(prices)
        return prices

    def set_price_panel(self, prices: pd.DataFrame) -> None:
        """Set the price panel and derive returns / expected returns / covariance."""
        self.tickers = list(prices.columns)
        self.prices_df = prices
        self.returns_df = prices.pct_change().dropna()
        self.mu = expected_returns.mean_historical_return(prices, compounding=False)
        self.S = risk_models.sample_cov(prices)

    def _load_yfinance(self, lookback_days: int, start: "date | None" = None, end: "date | None" = None) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("yfinance is not installed; use data source 'db'") from exc
        period = f"{max(lookback_days // 21 + 1, 6)}mo"
        hist_kwargs = {"start": str(start), "end": str(end)} if (start and end) else {"period": period}
        # Fetch per symbol so a bad/untradeable ticker is skipped, not fatal.
        series = []
        for symbol in self.tickers:
            try:
                hist = yf.Ticker(symbol).history(auto_adjust=True, **hist_kwargs)
                if not hist.empty and "Close" in hist:
                    s = hist["Close"].rename(symbol)
                    s.index = s.index.tz_localize(None)
                    series.append(s)
            except Exception:
                continue
        if len(series) < 2:
            raise RuntimeError("yfinance returned insufficient data; try 'db' or a broader equity universe")
        prices = pd.concat(series, axis=1).ffill().dropna()
        if not (start and end) and lookback_days and len(prices) > lookback_days:
            prices = prices.tail(lookback_days)
        if prices.shape[1] < 2 or prices.empty:
            raise RuntimeError("yfinance returned insufficient data for optimization")
        return prices

    def _load_openbb(self, lookback_days: int, start: "date | None" = None, end: "date | None" = None) -> pd.DataFrame:
        try:
            from openbb import obb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openbb is not installed; use another data source") from exc
        series = []
        for symbol in self.tickers:
            try:
                kwargs: dict = {"symbol": symbol, "provider": "yfinance"}
                if start and end:
                    kwargs["start_date"], kwargs["end_date"] = str(start), str(end)
                df = obb.equity.price.historical(**kwargs).to_df()
                series.append(df["close"].rename(symbol))
            except Exception:
                continue
        if not series:
            raise RuntimeError("openbb returned no data for the requested universe")
        prices = pd.concat(series, axis=1).ffill().dropna()
        if not (start and end) and lookback_days and len(prices) > lookback_days:
            prices = prices.tail(lookback_days)
        return prices

    # ── expected-return models ──────────────────────────────────
    def compute_all_return_models(
        self, market_caps: dict[str, float] | None = None, views: dict[str, float] | None = None
    ) -> pd.DataFrame:
        prices = self.prices_df
        hist_mean = expected_returns.mean_historical_return(prices, compounding=False)
        real_cagr = expected_returns.mean_historical_return(prices, compounding=True)
        try:
            capm_ret = expected_returns.capm_return(prices, risk_free_rate=self.risk_free_rate)
        except Exception:
            capm_ret = expected_returns.capm_return(
                prices, market_prices=prices.mean(axis=1), risk_free_rate=self.risk_free_rate
            )

        market_prices = prices.mean(axis=1)
        delta = black_litterman.market_implied_risk_aversion(
            market_prices, risk_free_rate=self.risk_free_rate
        )
        if market_caps:
            mcap = pd.Series(market_caps).reindex(self.tickers).fillna(1.0)
        else:
            mcap = pd.Series(1.0, index=self.tickers)
        prior = black_litterman.market_implied_prior_returns(mcap, delta, self.S)
        if views:
            clean_views = {k: v for k, v in views.items() if k in self.tickers}
            bl_ret = (
                BlackLittermanModel(self.S, pi=prior, absolute_views=clean_views).bl_returns()
                if clean_views
                else prior
            )
        else:
            bl_ret = prior

        # Realized cumulative total return over the lookback window (真实历史收益).
        period_total = prices.iloc[-1] / prices.iloc[0] - 1.0
        # Historical backtest model: recency-weighted realized return (EMA of real prices).
        try:
            ema_ret = expected_returns.ema_historical_return(prices, span=min(len(prices), 180))
        except Exception:
            ema_ret = real_cagr

        return pd.DataFrame(
            {
                "Historical Mean (Arithmetic)": hist_mean,
                "Real Historical CAGR (Compound)": real_cagr,
                "CAPM Beta Model": capm_ret,
                "Black-Litterman Model": bl_ret,
                "Historical Backtest (EMA)": ema_ret,
                "Period Total Return": period_total,
            }
        )

    def set_return_model(
        self, method: str, market_caps: dict | None = None, views: dict | None = None
    ) -> None:
        models = self.compute_all_return_models(market_caps=market_caps, views=views)
        col = {
            "historical_mean": "Historical Mean (Arithmetic)",
            "real_cagr": "Real Historical CAGR (Compound)",
            "capm": "CAPM Beta Model",
            "black_litterman": "Black-Litterman Model",
            "backtest": "Historical Backtest (EMA)",
        }.get(method, "Historical Mean (Arithmetic)")
        self.mu = models[col]

    # ── metrics ─────────────────────────────────────────────────
    def calculate_individual_asset_metrics(self) -> pd.DataFrame:
        rows = []
        for col in self.prices_df.columns:
            r = self.returns_df[col]
            ann_ret = r.mean() * TRADING_DAYS
            ann_vol = r.std() * np.sqrt(TRADING_DAYS)
            sharpe = (ann_ret - self.risk_free_rate) / ann_vol if ann_vol > 0 else 0.0
            cum = (1 + r).cumprod()
            max_dd = ((cum - cum.cummax()) / cum.cummax()).min()
            var95 = np.percentile(r, 5)
            cvar95 = r[r <= var95].mean() if (r <= var95).any() else var95
            rows.append(
                {
                    "asset": col,
                    "expected_return": float(ann_ret),
                    "volatility": float(ann_vol),
                    "sharpe": float(sharpe),
                    "max_drawdown": float(max_dd),
                    "var_95": float(var95),
                    "cvar_95": float(cvar95),
                }
            )
        return pd.DataFrame(rows).set_index("asset")

    def calculate_risk_metrics(self, weights: dict[str, float]) -> dict[str, float]:
        cols = list(self.prices_df.columns)
        w = np.array([weights.get(c, 0.0) for c in cols])
        port_daily = (self.returns_df * w).sum(axis=1)
        exp_ret = float(np.sum(self.mu.to_numpy() * w))
        vol = float(np.sqrt(w @ self.S.to_numpy() @ w))
        sharpe = (exp_ret - self.risk_free_rate) / vol if vol > 0 else 0.0
        cum = (1 + port_daily).cumprod()
        max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
        var95 = float(np.percentile(port_daily, 5))
        cvar95 = float(port_daily[port_daily <= var95].mean()) if (port_daily <= var95).any() else var95
        return {
            "expected_return": exp_ret,
            "volatility": vol,
            "sharpe": float(sharpe),
            "max_drawdown": max_dd,
            "var_95": var95,
            "cvar_95": cvar95,
        }

    def normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        full = {c: float(weights.get(c, 0.0)) for c in self.prices_df.columns}
        total = sum(full.values())
        return {k: (v / total if total > 0 else 0.0) for k, v in full.items()}

    def evaluate_weights(self, weights: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
        norm = self.normalize_weights(weights)
        return norm, self.calculate_risk_metrics(norm)

    # ── optimization ────────────────────────────────────────────
    def build_portfolio_by_profile(
        self, profile: str, target_return: float | None = None
    ) -> tuple[dict[str, float], dict[str, float]]:
        if profile == "hrp":
            weights = _hrp_weights(self.returns_df)
            return weights, self.calculate_risk_metrics(weights)

        ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
        if profile == "conservative":
            ef.min_volatility()
        elif profile == "aggressive":
            ef.max_quadratic_utility(risk_aversion=1)
        elif profile == "target_return" and target_return is not None:
            ef.efficient_return(target_return=target_return)
        else:
            try:
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            except ValueError:
                # max_sharpe needs some expected return above the risk-free rate;
                # if none qualifies, fall back to max quadratic utility.
                ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
                ef.max_quadratic_utility(risk_aversion=1)
        weights = dict(ef.clean_weights())
        return weights, self.calculate_risk_metrics(weights)

    def check_if_efficient(self, weights: dict[str, float]) -> dict[str, Any]:
        _, current = self.evaluate_weights(weights)
        cur_ret, cur_vol = current["expected_return"], current["volatility"]
        out: dict[str, Any] = {"alpha_loss": None, "excess_vol": None}
        try:
            ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
            ef.efficient_return(target_return=cur_ret)
            m = self.calculate_risk_metrics(dict(ef.clean_weights()))
            out["excess_vol"] = cur_vol - m["volatility"]
        except Exception:
            pass
        try:
            ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
            ef.efficient_risk(target_volatility=cur_vol)
            m = self.calculate_risk_metrics(dict(ef.clean_weights()))
            out["alpha_loss"] = m["expected_return"] - cur_ret
        except Exception:
            pass
        return out

    def efficient_frontier_curve(self, points: int = 40) -> list[dict[str, float]]:
        mu = self.mu.to_numpy()
        lo, hi = float(mu.min()), float(mu.max())
        curve = []
        for target in np.linspace(lo, hi, points):
            try:
                ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
                ef.efficient_return(target_return=float(target))
                ret, vol, _ = ef.portfolio_performance(risk_free_rate=self.risk_free_rate)
                curve.append({"volatility": float(vol), "expected_return": float(ret)})
            except Exception:
                continue
        return curve

    def tangency_portfolio(self) -> dict[str, float] | None:
        """Max-Sharpe (tangency) portfolio point for drawing the capital market line."""
        try:
            ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
            try:
                ef.max_sharpe(risk_free_rate=self.risk_free_rate)
            except ValueError:
                ef = EfficientFrontier(self.mu, self.S, weight_bounds=self.weight_bounds)
                ef.max_quadratic_utility(risk_aversion=1)
            ret, vol, _ = ef.portfolio_performance(risk_free_rate=self.risk_free_rate)
            return {"volatility": float(vol), "expected_return": float(ret)}
        except Exception:
            return None

    def asset_points(self) -> list[dict[str, float]]:
        metrics = self.calculate_individual_asset_metrics()
        return [
            {"asset": idx, "volatility": float(row["volatility"]), "expected_return": float(row["expected_return"])}
            for idx, row in metrics.iterrows()
        ]

    def correlation_matrix(self) -> pd.DataFrame:
        return self.returns_df.corr()


# ── Native Hierarchical Risk Parity (López de Prado) ─────────────
def _quasi_diag(link: np.ndarray) -> list[int]:
    n = link.shape[0] + 1
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


def _hrp_weights(returns_df: pd.DataFrame) -> dict[str, float]:
    """HRP allocation: correlation-distance clustering + recursive bisection."""
    cov = returns_df.cov()
    corr = returns_df.corr()
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
            var_left, var_right = _cluster_var(cov, left), _cluster_var(cov, right)
            alpha = 1.0 - var_left / (var_left + var_right)
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha

    return {a: float(weights[a]) for a in assets}
