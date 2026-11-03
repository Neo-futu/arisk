"""投资风险 · 利率信用 Tab：久期/DV01/CS01/KRD/评级/发行人集中。"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_rates_credit_meta, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "src" / "modules" / "investment-risk" / "RiskDomainTabs.tsx"


def test_frontend_rates_credit_surfaces() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for token in (
        "getRatesCredit",
        "RatesCreditDomain",
        "portfolio_dv01",
        "portfolio_cs01",
        "krd_buckets",
        "issuer_investment_grade_pct",
        "debt_investment_grade_pct",
        "bond_agency_rating_rows",
        "rating_scale_legend",
        "issuer_concentration",
        "ratingSource",
        "SQL-RC-01",
    ):
        assert token in text, token


def test_rates_credit_seven_business_modules() -> None:
    rc = import_module("3_riskengine.risk.rates_credit")
    meta = sample_rates_credit_meta()
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .rates_credit(meta=meta, rating_source="all", top_n=10)
    )
    check = rc.verify_business_modules(pack)
    assert check["passed"], check["errors"]
    assert pack["tab"] == "rates-credit"
    assert pack["page"] == "/investment-risk/indicators"
    assert pack["business_modules"] == list(rc.BUSINESS_MODULES)

    book = pack["modules"]["bond_book"]
    assert book["bond_count"] == 7
    assert book["total_bond_market_value"] == pytest.approx(136_640_000.0)
    assert book["bond_exposure_pct_nav"] == pytest.approx(4.98, abs=0.01)

    sens = pack["modules"]["sensitivity"]
    assert sens["weighted_duration_years"] == pytest.approx(1.804, abs=0.001)
    assert sens["portfolio_dv01"] == pytest.approx(24_648.0, abs=0.5)
    assert sens["portfolio_cs01"] == pytest.approx(19_718.4, abs=0.5)
    assert sens["portfolio_cs01"] == pytest.approx(sens["portfolio_dv01"] * 0.8, abs=1e-6)

    # HTTP 同形顶层字段
    assert pack["portfolio_dv01"] == sens["portfolio_dv01"]
    assert pack["bond_count"] == 7
    assert pack["issuer_investment_grade_pct"] == pytest.approx(100.0)
    assert pack["debt_investment_grade_pct"] == pytest.approx(100.0)

    dist = pack["modules"]["rating_distribution"]
    by_rating = {row["rating"]: row for row in dist["issuer_rating_distribution"]}
    assert by_rating["AAA"]["weight_pct"] == pytest.approx(65.30, abs=0.05)
    assert by_rating["AA+"]["weight_pct"] == pytest.approx(34.70, abs=0.05)

    krd = {row["bucket"]: row["weight_pct_bond"] for row in pack["krd_buckets"]}
    assert set(krd) == {"1M", "3M", "6M", "1Y", "1Y+"}
    assert krd["1M"] > 0
    assert krd["3M"] > 0
    assert krd["1Y+"] > 80.0

    agency = pack["modules"]["bond_agency_ratings"]
    assert agency["count"] == 7
    top = agency["rows"][0]
    assert top["security_code"] == "3141.HK"
    assert top["issuer_ratings"]["csci"] == "AAA"
    assert top["issuer_ratings"]["moody"] == "Aaa"
    assert top["debt_ratings"]["sp"] == "AAA"

    scale = pack["modules"]["rating_scale"]
    assert len(scale["rating_scale_legend"]) >= 18
    assert scale["rating_scale_legend"][0]["moody"] == "Aaa"
    assert "BBB-" in scale["rating_scale_note"]

    conc = pack["modules"]["issuer_concentration"]
    assert conc["top_issuers"][0]["issuer"] == "ABF Hong Kong Bond Index Fund"
    assert conc["top_issuers"][0]["weight_pct"] == pytest.approx(36.58, abs=0.05)
    assert conc["hhi"] > 0
    assert pack["rating_matched_bond_count"] == 7


def test_dv01_cs01_formulas() -> None:
    sens = import_module("3_riskengine.risk.rates_credit").module_sensitivity
    bonds = [
        {"market_value": 1_000_000.0, "duration": 5.0},
        {"market_value": 500_000.0, "duration": 2.0},
    ]
    pack = sens(bonds)
    # ΣMV=1.5e6；ΣMVD=6e6；加权=4；DV01=600；CS01=480
    assert pack["weighted_duration_years"] == pytest.approx(4.0)
    assert pack["portfolio_dv01"] == pytest.approx(600.0)
    assert pack["portfolio_cs01"] == pytest.approx(480.0)


def test_maturity_bucket_boundaries() -> None:
    bucket = import_module("3_riskengine.risk.rates_credit").maturity_bucket
    assert bucket(0) == "1M"
    assert bucket(30) == "1M"
    assert bucket(31) == "3M"
    assert bucket(90) == "3M"
    assert bucket(91) == "6M"
    assert bucket(180) == "6M"
    assert bucket(181) == "1Y"
    assert bucket(365) == "1Y"
    assert bucket(366) == "1Y+"


def test_rating_source_filter_and_moody_symbols() -> None:
    rc = import_module("3_riskengine.risk.rates_credit")
    meta = sample_rates_credit_meta()
    # 将持仓主机构改为穆迪，验证来源过滤 + Aaa 符号
    for bond in meta["bonds"]:
        bond["rating_agency"] = "MOODY"
        bond["issuer_rating"] = "Aaa" if bond["issuer_rating"] == "AAA" else "Aa1"
        bond["debt_rating"] = bond["issuer_rating"]
        bond["rating"] = bond["issuer_rating"]
    pack = (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(sample_snapshot())
        .risk()
        .rates_credit(meta=meta, rating_source="moody")
    )
    assert pack["rating_source"] == "moody"
    assert pack["rating_matched_bond_count"] == 7
    ratings = {row["rating"] for row in pack["issuer_rating_distribution"]}
    assert "Aaa" in ratings or "Aa1" in ratings
    assert "AAA" not in ratings  # 穆迪来源不用 SP 符号拆桶


def test_is_investment_grade_boundary() -> None:
    ig = import_module("3_riskengine.risk.rates_credit").is_investment_grade
    assert ig("BBB-") is True
    assert ig("Baa3") is True
    assert ig("BB+") is False
    assert ig("Ba1") is False


def test_domain_rates_credit_includes_pack() -> None:
    pack = import_module("4_business.investment_risk.rates_credit").analyze(sample_snapshot())
    assert pack["domain"] == "rates_credit"
    assert "rates_credit" in pack
    assert pack["rates_credit"]["modules"]["sensitivity"]["portfolio_dv01"] is not None
    assert set(pack["kpis"]) >= {"Duration", "DV01", "KRD", "CS01"}
