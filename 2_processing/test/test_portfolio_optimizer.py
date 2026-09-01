"""Unit tests for the portfolio optimization engine (synthetic data, no network)."""
from importlib import import_module

import numpy as np
import pytest

po = import_module("2_processing.tools.performance.portfolio_optimizer")

UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _pm():
    pm = po.PortfolioManager(UNIVERSE, risk_free_rate=0.04, weight_bounds=(0.0, 0.5))
    pm.load_prices("synthetic", lookback_days=400)
    pm.set_return_model("historical_mean")
    return pm


def test_synthetic_prices_are_reproducible() -> None:
    a = po.build_synthetic_prices(UNIVERSE, 300)
    b = po.build_synthetic_prices(UNIVERSE, 300)
    assert a.shape == b.shape == (300, 5)
    assert np.allclose(a.to_numpy(), b.to_numpy())


def test_hrp_weights_sum_to_one_and_nonnegative() -> None:
    pm = _pm()
    w = po._hrp_weights(pm.returns_df)
    assert set(w) == set(UNIVERSE)
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert all(v >= -1e-9 for v in w.values())


def test_hrp_single_asset() -> None:
    pm = po.PortfolioManager(["ONLY"], weight_bounds=(0, 1))
    pm.load_prices("synthetic", lookback_days=200)
    w = po._hrp_weights(pm.returns_df)
    assert w == {"ONLY": 1.0}


def test_risk_metrics_shape_and_var_cvar_ordering() -> None:
    pm = _pm()
    m = pm.calculate_risk_metrics({c: 0.2 for c in UNIVERSE})
    assert set(m) == {"expected_return", "volatility", "sharpe", "max_drawdown", "var_95", "cvar_95"}
    # CVaR (mean of the worst tail) must be <= VaR (the 5th percentile).
    assert m["cvar_95"] <= m["var_95"] + 1e-9
    assert m["volatility"] >= 0


def test_return_models_has_expected_columns() -> None:
    pm = _pm()
    rm = pm.compute_all_return_models(views={"AAA": 0.15})
    assert list(rm.columns) == [
        "Historical Mean (Arithmetic)",
        "Real Historical CAGR (Compound)",
        "CAPM Beta Model",
        "Black-Litterman Model",
        "Historical Backtest (EMA)",
        "Period Total Return",
    ]
    assert rm.shape[0] == len(UNIVERSE)


@pytest.mark.parametrize("profile", ["conservative", "balanced", "aggressive", "hrp"])
def test_profiles_weights_normalized(profile: str) -> None:
    pm = _pm()
    w, m = pm.build_portfolio_by_profile(profile)
    assert abs(sum(w.values()) - 1.0) < 1e-4
    assert "sharpe" in m


def test_normalize_weights() -> None:
    pm = _pm()
    norm = pm.normalize_weights({"AAA": 1, "BBB": 1, "CCC": 2})
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    assert norm["CCC"] == pytest.approx(0.5)


def test_return_models_include_period_total_return() -> None:
    pm = _pm()
    rm = pm.compute_all_return_models()
    assert "Period Total Return" in rm.columns
    assert rm["Period Total Return"].notna().all()


def test_tangency_portfolio_returns_finite_point() -> None:
    pm = _pm()
    tan = pm.tangency_portfolio()
    assert tan is not None
    assert tan["volatility"] > 0
    assert np.isfinite(tan["expected_return"])


def test_evaluate_weights_normalized_metrics() -> None:
    pm = _pm()
    norm, metrics = pm.evaluate_weights({"AAA": 2, "BBB": 2})
    assert abs(sum(norm.values()) - 1.0) < 1e-6
    assert set(metrics) == {"expected_return", "volatility", "sharpe", "max_drawdown", "var_95", "cvar_95"}
