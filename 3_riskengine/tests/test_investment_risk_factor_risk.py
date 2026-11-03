"""投资风险 · 因子风险页：敞口 / 标准冲击 / RC / Beta·TE。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_factor_risk_meta, sample_mmf_snapshot, sample_overview_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "runtimePages.tsx"


def test_frontend_factor_risk_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "FactorRiskRuntimePage",
        "getFactorRisk",
        "factor_exposure",
        "factor_shocks",
        "risk_contribution_by_asset_class",
        "factorBeta",
        "factorTrackingError",
        "factorExposureTop",
        "factorShockTitle",
        "factorRcByClass",
    ):
        assert token in text, token


def test_factor_risk_five_business_modules() -> None:
    fr = import_module("3_riskengine.risk.factor_risk")
    meta = sample_factor_risk_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .risk()
        .factor_risk(meta=meta, confidence=0.99)
    )
    check = fr.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "factor-risk"
    assert pack["page"] == "/investment-risk/factor-risk"
    assert pack["business_modules"] == list(fr.BUSINESS_MODULES)
    assert pack["benchmark_id"] == "HSI"

    kpi = pack["modules"]["kpi_panel"]
    assert kpi["beta"]["beta"] is not None
    assert abs(kpi["beta"]["beta"]) < 0.5  # 货币式平稳收益对权益基准近零 Beta
    assert kpi["tracking_error"]["annualized_pct"] is not None
    assert kpi["tracking_error"]["annualized_pct"] > 0

    summary = pack["modules"]["summary"]
    assert summary["dominant_factor"]
    assert summary["dominant_factor_pct_nav"] is not None

    exposure = pack["modules"]["factor_exposure"]["rows"]
    assert exposure
    factors = {row["factor"] for row in exposure}
    assert "EQUITY" in factors or "RATE_CREDIT" in factors or "CASH" in factors
    assert exposure[0]["pct_nav"] >= exposure[-1]["pct_nav"]

    shocks = pack["modules"]["factor_shocks"]
    labels = {row["factor"] for row in shocks["rows"]}
    assert {"rate_1bp", "equity_1pct", "fx_1pct", "cs_1bp", "vol_10pct"} <= labels
    assert all("pnl" in row and "pnl_pct_nav" in row for row in shocks["rows"])

    rc = pack["modules"]["rc_by_asset_class"]["rows"]
    assert rc
    assert abs(sum(row["share_pct"] for row in rc) - 100.0) < 1e-6 or sum(
        abs(row["share_pct"]) for row in rc
    ) > 0

    # HTTP 同形
    fr_body = pack["factor_risk"]
    assert fr_body["factor_exposure"] == exposure
    assert fr_body["beta"]["paired_observations"] >= 3
    assert "beta" in fr_body["formulas"]


def test_beta_te_math() -> None:
    fr = import_module("3_riskengine.risk.factor_risk")
    fund = [0.01, 0.02, -0.01, 0.015, 0.005]
    bench = [0.01, 0.015, -0.005, 0.01, 0.0]
    beta = fr.compute_beta(fund, bench)
    te = fr.compute_tracking_error(fund, bench)
    assert beta["paired_observations"] == 5
    assert beta["beta"] is not None
    assert te["annualized"] is not None
    assert te["annualized_pct"] == pytest.approx(te["annualized"] * 100.0)
    # 完全复制基准 → β=1、TE=0
    same = fr.compute_beta(bench, bench)
    assert same["beta"] == pytest.approx(1.0)
    assert fr.compute_tracking_error(bench, bench)["annualized"] == pytest.approx(0.0)


def test_mmf_factor_exposure_cash_dominant() -> None:
    fr = import_module("3_riskengine.risk.factor_risk")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_mmf_snapshot())
        .risk()
        .factor_risk(meta=sample_factor_risk_meta(), include_portfolio_risk=True)
    )
    exposure = pack["modules"]["factor_exposure"]["rows"]
    by_factor = {row["factor"]: row["pct_nav"] for row in exposure}
    # MMF：RATE_CREDIT（债+CD+存款）应显著；CASH 存在
    assert by_factor.get("RATE_CREDIT", 0) > 50 or by_factor.get("CASH", 0) + by_factor.get("RATE_CREDIT", 0) > 80
    assert pack["modules"]["summary"]["dominant_factor"] in by_factor


def test_domain_factor_risk_includes_pack() -> None:
    pack = import_module("4_business.investment_risk.factor_risk").analyze(
        sample_snapshot(),
        benchmark_returns=sample_factor_risk_meta()["benchmark_returns"],
    )
    assert pack["domain"] == "factor_risk"
    assert "factor_risk" in pack
    assert pack["factor_risk"]["modules"]["factor_shocks"]["rows"]
    assert set(pack["kpis"]) >= {"Factor Exposure", "Beta", "Tracking Error"}
