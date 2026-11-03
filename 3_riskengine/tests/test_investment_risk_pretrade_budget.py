"""投资风险 · 风险预算与前置试算：决策闸门 / RC / VaR / DV01。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_mmf_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "runtimePages.tsx"


def test_frontend_pretrade_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "PretradeBudgetRuntimePage",
        "getPretradeCheck",
        "risk_budget",
        "projected_risk_budget",
        "decision_summary",
        "budget_utilization",
        "factor_shocks_current",
        "rp_reference",
        "pretrade-budget",
        "risk-budget",
    ):
        assert token in text, token


def test_pretrade_ten_business_modules() -> None:
    pt = import_module("3_riskengine.risk.pretrade")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .pretrade_budget(
            trade_amount=50_000.0,
            trade_side="BUY",
            asset_class="BOND",
            duration_years=2.0,
            issuer_name="HKMA",
        )
    )
    check = pt.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "risk-budget"
    assert pack["page"] == "/investment-risk/pretrade-budget"
    assert pack["business_modules"] == list(pt.BUSINESS_MODULES)
    assert pack["decision"] in {"ALLOW", "ALLOW_WITH_WARNING", "BLOCK"}

    cards = pack["modules"]["decision_cards"]
    assert cards["remaining_duration_budget"] is not None
    assert cards["dv01_from"] is not None
    assert cards["dv01_to"] is not None

    assert pack["modules"]["kpi_panel"]["rows"]
    assert pack["modules"]["risk_budget"]["by_asset_class"]
    assert pack["modules"]["projected_budget"]["by_asset_class"]
    assert pack["modules"]["decision_summary"]["headline"]
    assert pack["modules"]["factor_shock_compare"]["rows"]
    assert pack["modules"]["limit_comparison"]["rows"]
    assert pack["modules"]["methodology"]["logic"]["steps"]

    # HTTP PretradeRiskResult 同形
    assert "current" in pack and "projected" in pack and "limits" in pack
    assert pack["risk_budget"]["by_asset_class"]
    assert pack["decision_summary"]["rationale"]
    assert pack["engine_metrics"]["factor_shocks_current"] is not None
    assert pack["adapter_usage"]["financepy"]


def test_apply_proposed_trade_independent() -> None:
    pt = import_module("3_riskengine.risk.pretrade")
    snap = sample_snapshot()
    proposed = pt.apply_proposed_trade(
        snap,
        {
            "security_code": "PRETRADE_TEST",
            "security_name": "试算债",
            "side": "BUY",
            "amount": 100_000.0,
            "asset_class": "BOND",
            "duration": 2.0,
            "issuer": "TEST_ISSUER",
            "currency": "HKD",
        },
    )
    assert proposed is not snap
    codes = {p.security_code for p in proposed.positions}
    assert "PRETRADE_TEST" in codes
    assert proposed.data_quality.get("source") == "proposed_trade"
    assert proposed.data_quality.get("is_live") is False
    # 现金对冲
    cash = next(p for p in proposed.positions if p.asset_class == "CASH")
    assert cash.market_value_base == pytest.approx(0.0)


def test_block_on_large_impact() -> None:
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .pretrade_budget(
            trade_amount=800_000.0,  # 80% NAV → 冲击超 5%
            trade_side="BUY",
            asset_class="BOND",
            duration_years=2.0,
            issuer_name="NEW_ISSUER",
            limits={
                "duration_years": 4.0,
                "issuer_pct_nav": 10.0,
                "tracking_error_proxy_pct": 5.0,
                "var_pct_nav": 2.0,
            },
        )
    )
    assert pack["decision"] in {"ALLOW_WITH_WARNING", "BLOCK"}
    assert pack["breach_flags"]
    assert any("冲击" in flag or "发行人" in flag for flag in pack["breach_flags"])


def test_allow_small_mmf_trade() -> None:
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_mmf_snapshot())
        .risk()
        .pretrade_budget(
            trade_amount=10_000.0,
            trade_side="BUY",
            asset_class="BOND",
            duration_years=0.25,
            # 新发行人、小名义：不触发已有大发行人集中度
            issuer_name="NEW_SMALL_ISSUER",
        )
    )
    assert pack["decision"] == "ALLOW"
    assert pack["budget_utilization"]["duration_remaining_years"] is not None
    assert pack["projected"]["duration_years"] is not None
    assert pack["modules"]["rp_reference"] is not None


def test_domain_risk_budget_includes_pack() -> None:
    pack = import_module("4_business.investment_risk.risk_budget").analyze(sample_snapshot())
    assert pack["domain"] == "risk_budget"
    assert "pretrade_budget" in pack
    assert pack["pretrade_budget"]["modules"]["kpi_panel"]["rows"]
