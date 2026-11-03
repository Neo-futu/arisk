"""投资风险 · 基本面因子与行为：Momentum/LowVol/Size、HHI、拥挤度。"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_factor_behavior_meta, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "runtimePages.tsx"


def test_frontend_factor_behavior_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "FactorBehaviorRuntimePage",
        "getFactorBehavior",
        "style_exposure",
        "sector_concentration",
        "crowding_top",
        "momentumExposure",
        "lowVolExposure",
        "sizeExposure",
        "sectorHhi",
        "crowdingTop",
        "styleFactorExposure",
    ):
        assert token in text, token


def test_factor_behavior_five_business_modules() -> None:
    fb = import_module("3_riskengine.risk.factor_behavior")
    meta = sample_factor_behavior_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .factor_behavior(meta=meta)
    )
    check = fb.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "factor-behavior"
    assert pack["page"] == "/investment-risk/factor-behavior"
    assert pack["business_modules"] == list(fb.BUSINESS_MODULES)

    summary = pack["modules"]["summary"]
    assert summary["momentum_exposure"] is not None
    assert summary["momentum_exposure"] < 0  # 价格下行
    assert summary["low_volatility_exposure"] is not None
    assert 0.5 < summary["low_volatility_exposure"] < 1.0
    assert summary["size_exposure"] is not None
    assert summary["size_exposure"] == pytest.approx(
        __import__("math").log(380_000_000.0), rel=1e-6
    )
    assert summary["sector_hhi"] == pytest.approx(10000.0)
    assert summary["turnover_pct"] == pytest.approx(0.0)

    style = pack["modules"]["style_exposure"]
    assert style["coverage_weight"] == pytest.approx(100.0)
    assert style["growth_weight_pct"] == pytest.approx(100.0)
    assert style["value_weight_pct"] == pytest.approx(0.0)
    assert {row["factor"] for row in style["bars"]} == {"Momentum", "LowVol", "Size", "Coverage"}

    sector = pack["modules"]["sector_concentration"]
    assert sector["weights"][0]["sector"] == "Information Technology"
    assert sector["weights"][0]["weight_pct"] == pytest.approx(100.0)

    trading = pack["modules"]["trading_behavior"]
    assert trading["crowding_count"] == 1
    top = trading["crowding_top"][0]
    assert top["security_code"] == "0700.HK"
    assert top["crowding_ratio"] == pytest.approx(1_000_000.0 / 80_000_000.0, abs=1e-6)

    assert "行业集中度偏高（HHI > 1800）" in pack["warnings"]
    assert pack["logic"]["steps"]
    assert "momentum" in pack["formulas"]

    # HTTP 同形
    assert pack["style_exposure"]["momentum_exposure"] == summary["momentum_exposure"]
    assert pack["sector_concentration"]["hhi"] == 10000.0


def test_style_formulas_two_names() -> None:
    fb = import_module("3_riskengine.risk.factor_behavior")
    holdings = [
        {"security_code": "A", "security_name": "A", "sector": "IT", "quantity": 100, "market_value": 60_000},
        {"security_code": "B", "security_name": "B", "sector": "Finance", "quantity": 50, "market_value": 40_000},
    ]
    prices = {
        "A": [(date(2026, 1, 1), 100.0), (date(2026, 2, 1), 110.0), (date(2026, 3, 1), 121.0)],
        "B": [(date(2026, 1, 1), 50.0), (date(2026, 2, 1), 50.0), (date(2026, 3, 1), 50.0)],
    }
    volumes = {"A": [1000.0, 1000.0], "B": [500.0, 500.0]}
    core = fb.analyze_book(holdings, prices_by_security=prices, volumes_by_security=volumes, turnover_pct=10.0)
    # A: R=0.21, B: R=0；w=0.6/0.4
    assert core["style_exposure"]["momentum_exposure"] == pytest.approx(0.6 * 0.21)
    assert core["sector_concentration"]["hhi"] == pytest.approx((0.6**2 + 0.4**2) * 10000)
    assert core["trading_behavior"]["crowding_top"][0]["security_code"] in {"A", "B"}


def test_empty_book_warns() -> None:
    fb = import_module("3_riskengine.risk.factor_behavior")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .factor_behavior(meta={"holdings": [], "period_end": "2026-11-02"})
    )
    assert "区间末无股票持仓" in pack["warnings"][0]
    assert pack["modules"]["summary"]["momentum_exposure"] is None


def test_domain_factor_behavior_includes_pack() -> None:
    pack = import_module("4_business.investment_risk.factor_behavior").analyze(sample_snapshot())
    assert pack["domain"] == "factor_behavior"
    assert "factor_behavior" in pack
    assert pack["factor_behavior"]["modules"]["methodology"]["formulas"]["hhi"]
    assert set(pack["kpis"]) >= {"Factor Exposure", "Concentration", "Beta"}
