"""投资风险整体风险敞口：组合 / 币种 / 成立日 / WAM·WAL / 投资管理人员。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_basic_info_meta, sample_mmf_snapshot, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "routes" / "_layout" / "investment-risk.indicators.tsx"


def test_frontend_indicators_surfaces_basic_info_modules() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "getBasicInfo",
        "basicInfo",
        "base_currency",
        "inception_date",
        "mmf_wam_limit_days",
        "mmf_wal_limit_days",
        "managers",
        "risk-exposure",
        "FUND_MANAGER",
    ):
        assert token in text, token


def test_basic_info_five_business_modules() -> None:
    basic_info = import_module("3_riskengine.portfolio.basic_info")
    meta = sample_basic_info_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_mmf_snapshot())
        .portfolio()
        .basic_info(meta=meta)
    )
    check = basic_info.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["business_modules"] == list(basic_info.BUSINESS_MODULES)
    assert pack["page"] == "/investment-risk/indicators#risk-exposure"

    portfolio = pack["modules"]["portfolio"]
    assert portfolio["fund_id"] == "BHMMF001"
    assert portfolio["port_name"] == "博晖港币货币基金"
    assert portfolio["fund_category"] == "MONEY_MARKET"
    assert portfolio["is_mmf"] is True

    currency = pack["modules"]["currency"]
    assert currency["base_currency"] == "HKD"
    assert currency["data_date"] == "2026-09-01"

    inception = pack["modules"]["inception"]
    assert inception["inception_date"] == "2020-03-15"
    assert inception["status"] == "ACTIVE"
    assert inception["tenure_days"] is not None and inception["tenure_days"] > 0

    wam_wal = pack["modules"]["wam_wal"]
    assert wam_wal["is_mmf"] is True
    assert wam_wal["mmf_wam_limit_days"] == pytest.approx(60.0)
    assert wam_wal["mmf_wal_limit_days"] == pytest.approx(120.0)
    assert wam_wal["wam_days"] is not None
    assert wam_wal["wal_days"] is not None
    assert wam_wal["wam_days"] > 0
    assert wam_wal["wal_days"] >= wam_wal["wam_days"]
    assert wam_wal["status"] in {"ok", "warn", "breach"}

    managers = pack["modules"]["managers"]
    assert managers["count"] == 3
    assert managers["current_count"] == 2
    assert "张经理" in managers["lead_names"]
    assert pack["managers"][0]["person_name"]  # HTTP 同形

    http_portfolio = pack["portfolio"]
    assert http_portfolio["base_currency"] == "HKD"
    assert http_portfolio["inception_date"] == "2020-03-15"
    assert http_portfolio["mmf_wam_limit_days"] == pytest.approx(60.0)


def test_non_mmf_basic_info_skips_wam_values() -> None:
    basic_info = import_module("3_riskengine.portfolio.basic_info")
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .portfolio()
        .basic_info(
            meta={
                "port_name": "混合组合",
                "port_type": "MIXED",
                "inception_date": "2019-01-01",
                "managers": [],
            }
        )
    )
    check = basic_info.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["modules"]["portfolio"]["fund_category"] == "MIXED"
    assert pack["modules"]["wam_wal"]["is_mmf"] is False
    assert pack["modules"]["wam_wal"]["wam_days"] is None
    assert pack["modules"]["managers"]["count"] == 0


def test_category_map_equity() -> None:
    basic_info = import_module("3_riskengine.portfolio.basic_info")
    assert basic_info.resolve_fund_category(port_type="ETF", is_mmf=False) == "EQUITY"
    assert basic_info.resolve_fund_category(port_type="BOND", is_mmf=False) == "BOND"
    assert basic_info.resolve_fund_category(port_type="OTHER", is_mmf=True) == "MONEY_MARKET"


def test_domain_exposure_includes_basic_info() -> None:
    pack = import_module("4_business.investment_risk.exposure").analyze(
        sample_mmf_snapshot(),
    )
    assert pack["domain"] == "exposure"
    assert "Gross Exposure" in pack["kpis"]
    bi = pack["basic_info"]
    assert bi["modules"]["portfolio"]["fund_id"] == "BHMMF001"
    assert bi["modules"]["wam_wal"]["is_mmf"] is True
    assert "risk_indicators" in pack
    assert len(pack["risk_indicators"]["modules"]["metric_board"]["categories"]) == 6
