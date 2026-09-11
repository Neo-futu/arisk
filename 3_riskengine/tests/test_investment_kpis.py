"""Wave 4 Investment Risk KPI regression tests."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import sample_snapshot

REQUIRED_FIELDS = ("kpi", "input", "calculation", "engine", "formula", "result", "data_quality")
KPI_IDS = import_module("3_riskengine.risk.kpis").KPI_IDS


def _pack(**kwargs):
    kpis = import_module("3_riskengine.risk.kpis")
    return kpis.compute_kpi_pack(sample_snapshot(), **kwargs)


@pytest.mark.parametrize("kpi_id", KPI_IDS)
def test_each_kpi_has_required_audit_fields(kpi_id: str) -> None:
    report = _pack()["kpis"][kpi_id]
    for field in REQUIRED_FIELDS:
        assert field in report, field
        assert report[field] is not None or field == "result"
    assert report["kpi"] == kpi_id
    assert report["formula"]
    assert report["engine"]
    assert report["calculation"]
    assert "input" in report
    assert isinstance(report["data_quality"], dict)


def test_var_cvar_es_regression() -> None:
    kpis = _pack()["kpis"]
    var = kpis["VaR"]["result"]
    cvar = kpis["CVaR"]["result"]
    es = kpis["ES"]["result"]
    assert var["amount"] is not None
    assert cvar["amount"] >= var["amount"] - 1e-9
    assert es["amount"] == pytest.approx(cvar["amount"])
    assert kpis["VaR"]["engine"]
    assert kpis["CVaR"]["formula"].startswith("CVaR")


def test_volatility_drawdown_regression() -> None:
    kpis = _pack()["kpis"]
    assert kpis["Volatility"]["result"]["annualized"] > 0
    assert kpis["Drawdown"]["result"]["max_drawdown"] < 0


def test_beta_and_tracking_error_with_identical_benchmark() -> None:
    snapshot = sample_snapshot()
    returns = [item[1] for item in snapshot.nav_returns]
    kpis = import_module("3_riskengine.risk.kpis")
    pack = kpis.compute_kpi_pack(snapshot, benchmark_returns=returns)
    assert pack["kpis"]["Beta"]["result"]["beta"] == pytest.approx(1.0)
    assert pack["kpis"]["Tracking Error"]["result"]["annualized"] == pytest.approx(0.0, abs=1e-12)


def test_exposure_duration_dv01_krd_cs01_leverage() -> None:
    kpis = _pack()["kpis"]
    assert kpis["Gross Exposure"]["result"]["ratio"] == pytest.approx(1.0)
    assert kpis["Net Exposure"]["result"]["ratio"] == pytest.approx(1.0)
    assert kpis["Leverage"]["result"]["ratio"] == pytest.approx(1.0)
    assert kpis["Duration"]["result"]["weighted_years"] == pytest.approx(4.5)
    assert kpis["DV01"]["result"]["reval_pnl"] < 0
    assert kpis["CS01"]["result"]["reval_pnl"] < 0
    buckets = {item["tenor"]: item for item in kpis["KRD"]["result"]["buckets"]}
    assert buckets["5Y"]["pv01"] < 0
    assert "EQUITY" in kpis["Factor Exposure"]["result"]
    assert "RATE_CREDIT" in kpis["Factor Exposure"]["result"]


def test_liquidity_concentration_counterparty_pfe_epe() -> None:
    kpis = _pack()["kpis"]
    assert kpis["Liquidity"]["result"]["pct_nav"] == pytest.approx(10.0)
    assert kpis["Concentration"]["result"]["hhi"] > 0
    assert kpis["Counterparty Exposure"]["result"]["counterparty_count"] == 3
    assert kpis["PFE"]["result"]["amount"] > 0
    assert kpis["EPE"]["result"]["amount"] > 0
    assert kpis["EPE"]["result"]["amount"] <= kpis["PFE"]["result"]["amount"] + 1e-9
    assert kpis["Risk Contribution"]["result"]["rows"]


def test_business_domains_cover_all_kpis() -> None:
    domains = import_module("4_business.investment_risk.domains")
    covered = {kpi for ids in domains.MODULE_KPIS.values() for kpi in ids}
    assert set(KPI_IDS) <= covered
    snapshot = sample_snapshot()
    market = import_module("4_business.investment_risk.market_risk")
    report = market.analyze(snapshot)
    assert report["domain"] == "market_risk"
    assert set(report["kpis"]) == {"VaR", "CVaR", "ES", "Volatility", "Drawdown"}


def test_service_catalog_and_routes_are_compatible() -> None:
    service = import_module("4_business.investment_risk.service")
    catalog = service.kpi_catalog()
    assert catalog["frontend_routes"] == "/investment-risk/*"
    assert catalog["kpis"] == list(KPI_IDS)
    router = import_module("2_processing.api.routers.investment")
    paths = {route.path for route in router.router.routes}
    assert "/overview/{fund_id}" in paths
    assert "/kpis/{fund_id}" in paths
    assert "/kpi-catalog" in paths


def test_existing_investment_analysis_import_still_works() -> None:
    analysis = import_module("2_processing.tools.performance.investment_analysis")
    current = import_module("4_business.investment_risk").current_analysis
    assert current() is analysis
    assert hasattr(analysis, "compute_risk_indicators")
