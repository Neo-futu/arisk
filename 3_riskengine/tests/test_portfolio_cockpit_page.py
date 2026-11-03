"""组合驾驶舱业务模块：组合 / 规模 / 持仓资产类型 / 收益 / 净值。"""
from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_mmf_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PAGE = ROOT / "frontend" / "src" / "modules" / "portfolio-cockpit" / "PortfolioCockpitPage.tsx"


def test_frontend_surfaces_business_fields() -> None:
    text = FRONTEND_PAGE.read_text(encoding="utf-8")
    for token in (
        "net_asset",
        "unit_nav",
        "acc_unit_nav",
        "day_return",
        "period_return",
        "return_rate_7d",
        "port_type",
        "tabAum",
        "tabReturn",
        "tabNav",
    ):
        assert token in text, token


def test_five_business_modules_on_mixed_book() -> None:
    cockpit = import_module("3_riskengine.portfolio.cockpit")
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    pack = bound.portfolio().fundamentals(meta={"port_name": "Mixed Test", "port_type": "MIXED"})
    check = cockpit.verify_business_modules(pack)
    assert check["passed"], check["errors"]

    portfolio = pack["modules"]["portfolio"]
    scale = pack["modules"]["scale"]
    holdings = pack["modules"]["holdings_asset_mix"]
    returns = pack["modules"]["returns"]
    nav = pack["modules"]["nav"]

    assert portfolio["port_id"] == "TEST001"
    assert portfolio["base_currency"] == "HKD"
    assert scale["aum"] == pytest.approx(1_000_000.0)
    assert scale["gross_exposure"] > 0
    classes = {item["asset_class"] for item in holdings["classes"]}
    assert {"BOND", "EQUITY", "CASH"} <= classes
    weights = sum(item["weight"] for item in holdings["classes"])
    assert weights == pytest.approx(1.0, abs=1e-6)
    assert returns["day_return"] is not None
    assert returns["period_return"] is not None
    assert returns["observations"] == 300
    assert nav["unit_nav"] is not None
    assert len(nav["indexed"]) >= 2
    assert set(pack["charts"]) >= {"aum", "holdings_mix", "return", "nav"}


def test_mmf_book_holdings_are_look_through_fi() -> None:
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_mmf_snapshot())
        .portfolio()
        .fundamentals(meta={"port_name": "MMF", "port_type": "MMF", "is_mmf": True})
    )
    holdings = pack["modules"]["holdings_asset_mix"]
    classes = {item["asset_class"] for item in holdings["classes"]}
    assert "BOND" in classes or "CD" in classes or "DEPOSIT" in classes
    assert pack["modules"]["portfolio"]["is_mmf"] is True
    assert pack["sfc_status"] in {"ok", "warn", "breach"}
    assert pack["modules"]["scale"]["aum"] == pytest.approx(1_000_000.0)


def test_period_return_and_yield_math() -> None:
    cockpit = import_module("3_riskengine.portfolio.cockpit")
    history = [
        {"date": "2026-01-01", "unit_nav": 1.0, "net_asset": 100.0, "day_return": 0.0},
        {"date": "2026-02-01", "unit_nav": 1.1, "net_asset": 110.0, "day_return": 0.1},
        {"date": "2026-03-01", "unit_nav": 1.21, "net_asset": 121.0, "day_return": 0.1},
    ]
    assert cockpit.period_return(history) == pytest.approx(0.21)
    indexed = cockpit.indexed_nav_series(history)
    assert indexed[-1]["indexed"] == pytest.approx(121.0)
    daily = [0.0001] * 7
    y7 = cockpit.yield_7d_annualized(daily)
    assert y7 is not None and y7 > 0


def test_overview_list_still_contracts() -> None:
    cockpit = import_module("3_riskengine.portfolio.cockpit")
    start = date(2026, 3, 1)
    hist = [
        {
            "date": (start + timedelta(days=i * 30)).isoformat(),
            "unit_nav": 1.0 + 0.01 * i,
            "net_asset": 1_000_000.0 * (1.0 + 0.01 * i),
            "day_return": 0.01 if i else 0.0,
        }
        for i in range(4)
    ]
    rows = [
        cockpit.build_row(
            port_id="TEST001",
            port_name="Mixed",
            port_type="MIXED",
            base_currency="HKD",
            as_of_date=date(2026, 9, 1),
            net_asset=1_000_000.0,
            unit_nav=1.03,
            history=hist,
        )
    ]
    overview = cockpit.overview_from_rows(rows, start_date=start, end_date=date(2026, 9, 1))
    assert cockpit.verify_overview_contract(overview)["passed"]
    assert overview["business_modules"] == list(cockpit.BUSINESS_MODULES)
