"""投资风险 · 业绩归因 Tab：Brinson / Campisi / 个券贡献 / Beta。"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_overview_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "RiskDomainTabs.tsx"
PANEL = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "AttributionModelPanel.tsx"


def test_frontend_attribution_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8") + "\n" + PANEL.read_text(encoding="utf-8")
    for token in (
        "getPerformanceAttribution",
        "AttributionModelPanel",
        "allocationEffect",
        "selectionEffect",
        "interactionEffect",
        "topWinners",
        "topLosers",
        "BHB",
        "Campisi",
        "carino",
        "EquityBetaContributionCard",
    ):
        assert token in text, token


def _two_period_frames():
    d0, d1 = date(2026, 3, 25), date(2026, 6, 25)
    portfolio = [
        {"date": d0, "symbol": "BOND5Y", "security_name": "Bond", "weight": 0.6, "asset": "BOND_CORP", "industry": "Sovereign", "return_period": 0.01,
         "total_return": 0.01, "income": 0.0075, "duration": 4.5, "treasury_change": -0.001, "spread_change": 0.0005, "convexity": 20.0},
        {"date": d0, "symbol": "0700.HK", "security_name": "Tencent", "weight": 0.3, "asset": "STOCK", "industry": "Information Technology", "return_period": -0.02,
         "total_return": -0.02, "income": 0.0, "duration": 0.0, "treasury_change": 0.0, "spread_change": 0.0, "convexity": 0.0},
        {"date": d0, "symbol": "CASH", "security_name": "Cash", "weight": 0.1, "asset": "CASH", "industry": "Cash", "return_period": 0.001,
         "total_return": 0.001, "income": 0.001, "duration": 0.0, "treasury_change": 0.0, "spread_change": 0.0, "convexity": 0.0},
        {"date": d1, "symbol": "BOND5Y", "security_name": "Bond", "weight": 0.55, "asset": "BOND_CORP", "industry": "Sovereign", "return_period": 0.008,
         "total_return": 0.008, "income": 0.0075, "duration": 4.4, "treasury_change": 0.0005, "spread_change": -0.0002, "convexity": 19.0},
        {"date": d1, "symbol": "0700.HK", "security_name": "Tencent", "weight": 0.35, "asset": "STOCK", "industry": "Information Technology", "return_period": 0.03,
         "total_return": 0.03, "income": 0.0, "duration": 0.0, "treasury_change": 0.0, "spread_change": 0.0, "convexity": 0.0},
        {"date": d1, "symbol": "CASH", "security_name": "Cash", "weight": 0.1, "asset": "CASH", "industry": "Cash", "return_period": 0.001,
         "total_return": 0.001, "income": 0.001, "duration": 0.0, "treasury_change": 0.0, "spread_change": 0.0, "convexity": 0.0},
    ]
    benchmark = [
        {"date": d0, "symbol": "B_BOND", "weight": 0.5, "asset": "BOND_CORP", "industry": "Sovereign", "return_period": 0.005},
        {"date": d0, "symbol": "B_EQ", "weight": 0.4, "asset": "STOCK", "industry": "Information Technology", "return_period": -0.05},
        {"date": d0, "symbol": "B_CASH", "weight": 0.1, "asset": "CASH", "industry": "Cash", "return_period": 0.0},
        {"date": d1, "symbol": "B_BOND", "weight": 0.5, "asset": "BOND_CORP", "industry": "Sovereign", "return_period": 0.004},
        {"date": d1, "symbol": "B_EQ", "weight": 0.4, "asset": "STOCK", "industry": "Information Technology", "return_period": 0.02},
        {"date": d1, "symbol": "B_CASH", "weight": 0.1, "asset": "CASH", "industry": "Cash", "return_period": 0.0},
    ]
    return portfolio, benchmark


def test_attribution_seven_business_modules() -> None:
    attr = import_module("3_riskengine.pnl.attribution")
    portfolio, benchmark = _two_period_frames()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_overview_snapshot())
        .pnl()
        .attribution(
            meta={
                "benchmark_id": "HSI",
                "portfolio_rows": portfolio,
                "benchmark_rows": benchmark,
                "period_start": "2026-03-25",
                "period_end": "2026-06-25",
                "beta_constituents": [
                    {"security_code": "0700.HK", "security_name": "騰訊控股", "weight_pct": 100.0, "beta": 0.259, "sample_size": 62}
                ],
                "equity_beta": 0.259,
            },
            brinson_method="BHB",
            brinson_multi=True,
            brinson_group="asset",
            campisi_benchmark=True,
            campisi_group="industry",
            contrib_mode="daily",
            contrib_link="carino",
        )
    )
    check = attr.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "attribution"
    assert pack["business_modules"] == list(attr.BUSINESS_MODULES)

    summary = pack["summary"]
    assert summary["fund_return_pct"] is not None
    assert summary["benchmark_return_pct"] is not None
    assert summary["active_return_pct"] is not None
    assert "allocation_effect_pct" in summary
    assert "selection_effect_pct" in summary
    assert "interaction_effect_pct" in summary

    assert pack["asset_contribution"]
    assert pack["top_winners"]
    assert pack["top_losers"]
    assert pack["top_winners"][0]["net_pnl"] >= pack["top_winners"][-1]["net_pnl"]

    brinson_views = pack["brinson_model"]["views"]
    assert any("BHB" in key and "grap" in key for key in brinson_views)
    bhb = next(iter(brinson_views.values()))
    # 配置+选券+交互 ≈ 超额（单期严格；多期 GRAP 对财富差）
    assert bhb["allocation"] + bhb["selection"] + bhb["interaction"] == pytest.approx(
        bhb["active_return"], abs=1e-6
    )

    campisi_views = pack["campisi_model"]["views"]
    assert any("bench" in key for key in campisi_views)
    camp = next(iter(campisi_views.values()))
    assert "income" in camp and "treasury" in camp and "spread" in camp

    contrib = pack["contribution_model"]
    assert contrib["groups"]
    assert abs(contrib["contribution_total"] + contrib["residual"] - contrib["portfolio_return"]) < 1e-6

    assert pack["equity_beta"]["value"] == pytest.approx(0.259)
    assert pack["equity_beta"]["constituents"][0]["security_code"] == "0700.HK"


def test_brinson_bhb_single_period_math() -> None:
    brinson = import_module("3_riskengine.pnl.attribution.brinson").brinson
    day = date(2026, 6, 25)
    port = [
        {"date": day, "symbol": "A", "weight": 0.6, "asset": "STOCK", "industry": "IT", "return_period": 0.10},
        {"date": day, "symbol": "B", "weight": 0.4, "asset": "BOND_CORP", "industry": "FI", "return_period": 0.02},
    ]
    bench = [
        {"date": day, "symbol": "A", "weight": 0.5, "asset": "STOCK", "industry": "IT", "return_period": 0.08},
        {"date": day, "symbol": "B", "weight": 0.5, "asset": "BOND_CORP", "industry": "FI", "return_period": 0.01},
    ]
    pack = brinson(port, bench, method="BHB", multi_period=False, group_by="asset")
    # Rp=0.6*0.10+0.4*0.02=0.068；Rb=0.5*0.08+0.5*0.01=0.045
    assert pack["portfolio_return"] == pytest.approx(0.068)
    assert pack["benchmark_return"] == pytest.approx(0.045)
    assert pack["active_return"] == pytest.approx(0.023)
    # BHB：配置+选券+交互 = 超额
    assert pack["allocation"] + pack["selection"] + pack["interaction"] == pytest.approx(0.023)
    stock = next(row for row in pack["groups"] if row["group"] == "STOCK")
    assert stock["allocation"] == pytest.approx((0.6 - 0.5) * 0.08)
    assert stock["selection"] == pytest.approx(0.5 * (0.10 - 0.08))
    assert stock["interaction"] == pytest.approx((0.6 - 0.5) * (0.10 - 0.08))


def test_contribution_carino_links_to_geometric() -> None:
    contribution = import_module("3_riskengine.pnl.attribution.contribution").contribution
    d0, d1 = date(2026, 1, 1), date(2026, 2, 1)
    rows = [
        {"date": d0, "symbol": "A", "weight": 1.0, "return_period": 0.10, "asset": "STOCK", "industry": "IT"},
        {"date": d1, "symbol": "A", "weight": 1.0, "return_period": -0.05, "asset": "STOCK", "industry": "IT"},
    ]
    pack = contribution(rows, mode="daily", link_method="carino", group_by="symbol")
    geometric = (1.1 * 0.95) - 1.0
    assert pack["portfolio_return"] == pytest.approx(geometric)
    assert pack["contribution_total"] == pytest.approx(geometric, abs=1e-9)
    assert pack["residual"] == pytest.approx(0.0, abs=1e-9)


def test_campisi_with_benchmark_selection_residual() -> None:
    campisi = import_module("3_riskengine.pnl.attribution.campisi").campisi
    day = date(2026, 6, 25)
    rows = [
        {
            "date": day,
            "symbol": "BOND",
            "weight": 1.0,
            "asset": "BOND",
            "industry": "Sovereign",
            "total_return": 0.02,
            "income": 0.01,
            "duration": 5.0,
            "treasury_change": -0.001,
            "spread_change": 0.0004,
            "convexity": 0.0,
        }
    ]
    pack = campisi(rows, benchmark=True, multi_period=False, group_by="industry")
    # treasury = -5*(-0.001)=0.005; spread=-5*0.0004=-0.002; sel=0.02-0.01-0.005-(-0.002)=0.007
    assert pack["treasury"] == pytest.approx(0.005)
    assert pack["spread"] == pytest.approx(-0.002)
    assert pack["selection"] == pytest.approx(0.007)


def test_domain_pnl_attribution_includes_pack() -> None:
    pack = import_module("4_business.investment_risk.pnl_attribution").analyze(sample_snapshot())
    assert pack["domain"] == "pnl_attribution"
    assert "attribution" in pack
    assert pack["attribution"]["modules"]["brinson_model"]["views"]
    assert pack["attribution"]["modules"]["summary"]["fund_return_pct"] is not None
