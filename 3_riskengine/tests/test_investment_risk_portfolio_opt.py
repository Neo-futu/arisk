"""组合配置与优化：收益模型 / 前沿 / 画像 / HRP 闸门。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_portfolio_opt_meta, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "portfolio-opt" / "PortfolioOptPage.tsx"


def test_frontend_portfolio_opt_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "analyzePortfolio",
        "governedOptimize",
        "efficient_frontier",
        "return_models",
        "asset_metrics",
        "correlation",
        "conservative",
        "balanced",
        "aggressive",
        "hrp",
        "Black-Litterman",
        "notTradeInstruction",
        "runGoverned",
    ):
        assert token in text, token


def test_portfolio_opt_nine_business_modules() -> None:
    po = import_module("3_riskengine.portfolio.optimization")
    meta = sample_portfolio_opt_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .portfolio()
        .portfolio_opt(meta=meta, run_governed=True, governed_method="hrp")
    )
    check = po.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["page"] == "/portfolio-opt"
    assert pack["business_modules"] == list(po.BUSINESS_MODULES)
    assert pack["is_trade_instruction"] is False

    assert len(pack["universe"]) == 10
    assert pack["modules"]["parameters"]["return_model"] == "historical_mean"
    assert pack["modules"]["parameters"]["risk_free_rate"] == pytest.approx(0.042)

    gate = pack["modules"]["governed_gate"]
    assert gate["status"] == "PROPOSAL"
    assert gate["is_trade_instruction"] is False
    assert abs(sum(gate["weights"].values()) - 1.0) < 1e-6
    assert gate["gate_status"]["optimization"] is True

    user = pack["modules"]["user_portfolio"]
    assert abs(sum(user["weights"].values()) - 1.0) < 1e-6
    assert "sharpe" in user["metrics"]

    frontier = pack["modules"]["efficient_frontier"]
    assert frontier["frontier"]
    assert frontier["tangency"] is not None
    assert len(frontier["asset_points"]) == 10

    returns_mod = pack["modules"]["return_models"]["rows"]
    assert {row["asset"] for row in returns_mod} == set(pack["universe"])
    assert all("historical_mean" in row and "black_litterman" in row for row in returns_mod)

    assets = pack["modules"]["asset_metrics"]["rows"]
    assert len(assets) == 10
    assert all("var_95" in row and "cvar_95" in row for row in assets)

    profiles = pack["modules"]["profile_comparison"]
    for name in ("conservative", "balanced", "aggressive", "hrp"):
        assert name in profiles["profiles"]
        assert abs(sum(profiles["profiles"][name]["weights"].values()) - 1.0) < 1e-6

    charts = pack["modules"]["charts"]
    assert charts["correlation"]["assets"]
    assert len(charts["correlation"]["matrix"]) == 10
    assert charts["allocation"]

    # HTTP 同形
    assert pack["profiles"]["hrp"]["metrics"]["volatility"] > 0
    assert pack["correlation"]["matrix"][0][0] == pytest.approx(1.0, abs=1e-9)


def test_hrp_and_min_vol_math() -> None:
    analytics = import_module("3_riskengine.portfolio.optimization.analytics")
    meta = sample_portfolio_opt_meta(120)
    returns = meta["returns"]
    hrp = analytics.hrp_weights(returns)
    assert abs(sum(hrp.values()) - 1.0) < 1e-8
    assert min(hrp.values()) >= -1e-12
    mu = analytics.historical_mean(returns)
    cov = analytics.sample_cov(returns)
    conservative = analytics._mv_optimize(mu, cov, objective="min_vol", weight_bounds=(0.0, 0.35))
    assert abs(sum(conservative.values()) - 1.0) < 1e-8
    assert max(conservative.values()) <= 0.35 + 1e-8


def test_evaluate_custom_weights_live_metrics() -> None:
    analytics = import_module("3_riskengine.portfolio.optimization.analytics")
    meta = sample_portfolio_opt_meta(100)
    returns = meta["returns"]
    prices = analytics.prices_from_returns(returns)
    rows = analytics.compute_return_models(prices, returns, risk_free_rate=0.04)
    mu = analytics.select_mu(rows, "historical_mean")
    cov = analytics.sample_cov(returns)
    # 全仓 AAPL
    weights = {a: (1.0 if a == "AAPL" else 0.0) for a in returns.columns}
    metrics = analytics.portfolio_metrics(weights, mu=mu, cov=cov, returns=returns, risk_free_rate=0.04)
    aapl = next(row for row in analytics.asset_metrics(returns, 0.04) if row["asset"] == "AAPL")
    assert metrics["expected_return"] == pytest.approx(aapl["expected_return"], abs=1e-9)
    assert metrics["volatility"] == pytest.approx(aapl["volatility"], abs=1e-9)
