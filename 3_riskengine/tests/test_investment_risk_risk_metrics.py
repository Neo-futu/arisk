"""投资风险 · 风险指标 Tab：核心五卡 / 滚动波动 / VaR三方法 / 六大风控类型。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_overview_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "routes" / "_layout" / "investment-risk.indicators.tsx"


def test_frontend_core_tab_surfaces_risk_modules() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "getRiskIndicators",
        "getRiskIndicatorTimeseries",
        "getVarCompare",
        "RiskMetricBoardSection",
        "interval_return_pct",
        "annualized_volatility_pct",
        "max_drawdown_pct",
        "equity_turnover",
        "equity_beta",
        "risk-exposure",
        "rollingVol",
    ):
        assert token in text, token


def test_risk_indicators_four_business_modules() -> None:
    ri = import_module("3_riskengine.portfolio.risk_indicators")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .portfolio()
        .risk_indicators(
            meta={
                "equity_turnover": {
                    "buy_amount": 80_000.0,
                    "sell_amount": 60_000.0,
                    "average_equity_balance": 300_000.0,
                }
            },
            confidence=0.99,
        )
    )
    check = ri.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["business_modules"] == list(ri.BUSINESS_MODULES)
    assert pack["tab"] == "core"

    core = pack["modules"]["core_profile"]
    assert core["sample_size"] >= 2
    assert core["annualized_volatility_pct"] is not None
    assert core["max_drawdown_pct"] is not None
    assert core["max_drawdown_pct"] <= 0  # 回撤为负或零
    assert core["equity_beta"]["value"] is not None
    assert core["equity_turnover"]["annualized_turnover_pct"] is not None

    rolling = pack["modules"]["rolling_volatility"]
    assert len(rolling["points"]) >= 10
    assert any(p.get("rolling_volatility_pct") is not None for p in rolling["points"])

    var_cmp = pack["modules"]["var_compare"]
    methods = {row["method_requested"]: row for row in var_cmp["results"]}
    assert {"historical", "monte_carlo", "distribution"} <= set(methods)
    assert methods["historical"]["var_pct_nav"] is not None
    assert methods["monte_carlo"]["var_pct_nav"] is not None
    assert methods["distribution"]["var_pct_nav"] is not None
    assert var_cmp["max_var_pct_nav"] == pytest.approx(
        max(row["var_pct_nav"] for row in var_cmp["results"] if row["var_pct_nav"] is not None)
    )

    board = pack["modules"]["metric_board"]
    cat_ids = [c["id"] for c in board["categories"]]
    assert cat_ids == ["market", "credit", "liquidity", "concentration", "compliance", "stress"]
    market = next(c for c in board["categories"] if c["id"] == "market")
    market_ids = {m["id"] for m in market["metrics"]}
    assert {"interval_return", "annualized_vol", "max_drawdown", "equity_beta", "duration"} <= market_ids
    credit = next(c for c in board["categories"] if c["id"] == "credit")
    assert any(m["id"] == "cs01" for m in credit["metrics"])
    assert board["credit_rating_detail"]["bond_count"] >= 1
    assert board["summary"]["total"] == sum(
        len(c["metrics"]) for c in board["categories"]
    )

    # HTTP 同形
    assert pack["indicators"]["interval_return_pct"] == core["interval_return_pct"]
    assert pack["var_compare"]["max_var_pct_nav"] == var_cmp["max_var_pct_nav"]
    assert len(pack["categories"]) == 6


def test_var_compare_methods_math() -> None:
    ri = import_module("3_riskengine.portfolio.risk_indicators")
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    pack = ri.module_var_compare(bound, confidence=0.99, horizon_days=1)
    hist = next(r for r in pack["results"] if r["method_requested"] == "historical")
    assert hist["var_hkd"] == pytest.approx(abs(hist["var_return"]) * 1_000_000.0)
    assert hist["var_pct_nav"] > 0


def test_metric_board_categories_have_groups() -> None:
    ri = import_module("3_riskengine.portfolio.risk_indicators")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .portfolio()
        .risk_indicators()
    )
    for category in pack["categories"]:
        assert category["metrics"], category["id"]
        assert any(m.get("group") for m in category["metrics"]), category["id"]


def test_metric_board_covers_page_metric_ids() -> None:
    """对齐页面风控指标清单：核心五卡、利率信用、因子、TTL、AMS、操作限额等。"""

    ri = import_module("3_riskengine.portfolio.risk_indicators")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .portfolio()
        .risk_indicators(
            meta={
                "extensions": {
                    "style_deviation": 100.0,
                    "style_detail": "成长 100.0% / 价值 0.0% / 大盘 100.0% / 小盘 0.0%",
                    "avg_pe": 18.6,
                    "avg_pb": 3.4,
                    "credit_spread": 0.8,
                    "implied_pd": 0.35,
                    "neg_news": 1,
                    "controller_conc": 89.02,
                    "controller_detail": "HSBC_GROUP",
                    "process_exceptions": 1,
                    "counterparty_limit_usage": 40.0,
                    "regulatory_redlines": 1,
                    "related_party_pct": 8.08,
                    "deposit_bank_usage": 75.0,
                    "equity_of_float": 0.0,
                    "equity_of_shares": 0.0001,
                    "net_redemption": -1.2,
                    "investor_top10": 55.0,
                    "top5_cover": 2.1,
                    "wam_internal_limit": 50,
                    "wal_internal_limit": 100,
                    "wla_internal_limit": 20,
                }
            }
        )
    )
    check = ri.verify_business_modules(pack)
    assert check["passed"], check["errors"]

    by_cat = {c["id"]: {m["id"]: m for m in c["metrics"]} for c in pack["categories"]}
    market = by_cat["market"]
    assert market["max_drawdown"]["value"] is not None
    assert market["day_return"]["value"] is not None
    assert market["sharpe"]["value"] is not None
    assert market["duration"]["value"] is not None
    assert market["dv01"]["value"] is not None
    assert market["credit_spread"]["value"] == pytest.approx(0.8)
    assert market["avg_pe"]["value"] == pytest.approx(18.6)
    assert market["style_deviation"]["value"] == pytest.approx(100.0)
    assert market["factor_rate_credit_exposure"]["value"] is not None
    assert market["daily_var_pct"]["value"] is not None
    assert market["rolling_vol_latest"]["value"] is not None

    credit = by_cat["credit"]
    assert credit["cs01"]["value"] is not None
    assert credit["implied_pd"]["value"] == pytest.approx(0.35)
    assert credit["neg_news"]["value"] == 1
    assert credit["controller_conc"]["value"] == pytest.approx(89.02)
    assert credit["controller_conc"]["detail"] == "HSBC_GROUP"

    liq = by_cat["liquidity"]
    assert liq["ttl_10"]["value"] is not None
    assert liq["cash_pct"]["value"] is not None
    assert liq["lcr_15"]["value"] is not None

    conc = by_cat["concentration"]
    assert conc["equity_top5"]["id"] == "equity_top5"
    assert conc["leverage"]["value"] is not None
    assert conc["repo_pct"]["value"] is not None

    compliance = by_cat["compliance"]
    assert "ams_wam" in compliance
    assert "ams_wla_internal" in compliance
    assert compliance["process_exceptions"]["value"] == 1
    assert compliance["related_party_pct"]["value"] == pytest.approx(8.08)
    assert compliance["deposit_bank_usage"]["value"] == pytest.approx(75.0)

    # 评级明细
    detail = pack["modules"]["metric_board"]["credit_rating_detail"]
    assert "issuer_rating_distribution" in detail
    assert "debt_rating_distribution" in detail


def test_domain_exposure_includes_risk_indicators() -> None:
    pack = import_module("4_business.investment_risk.exposure").analyze(sample_snapshot())
    assert pack["domain"] == "exposure"
    assert "risk_indicators" in pack
    assert pack["risk_indicators"]["modules"]["var_compare"]["results"]
    assert len(pack["risk_indicators"]["modules"]["metric_board"]["categories"]) == 6
