"""Wave 3 RiskEngine unit, deterministic, regression and cross-engine tests."""
from __future__ import annotations

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import SCENARIOS, Shock, RiskFactorType, ShockMode, sample_snapshot

ROOT = Path(__file__).resolve().parents[2]


def test_riskengine_imports_and_adapters_initialize() -> None:
    engine_mod = import_module("3_riskengine")
    engine = engine_mod.RiskEngine()
    status = engine.adapters_status()
    assert engine_mod.RISKENGINE_VERSION
    assert status["financepy"]["name"] == "financepy"
    assert status["riskfolio"]["name"] == "riskfolio"
    assert status["ore"]["name"] == "ore"
    assert engine.financepy.initialize().name == "financepy"
    assert engine.riskfolio.initialize().name == "riskfolio"
    assert engine.ore.initialize().name == "ore"
    assert engine.financepy.available is True
    assert engine.ore.available is True
    assert engine.ore.ore_swig_available is True
    assert engine.ore.describe()["pricing_backend"] == "ORE"


def test_ore_adapter_uses_installed_ore_swig() -> None:
    adapter = import_module("3_riskengine.adapters.ore").OREAdapter()
    probe = adapter.initialize()
    status = adapter.describe()
    assert probe.name == "ore"
    assert adapter.available is True
    assert adapter.ore_swig_available is True
    assert probe.error is None
    assert status["ore_swig"]["available"] is True
    assert status["pricing_backend"] == "ORE"


def test_valuation_api_price_revalue_greeks_pnl() -> None:
    valuation = import_module("3_riskengine.valuation")
    snapshot = sample_snapshot()
    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    priced = valuation.price(snapshot)
    revalued = valuation.revalue(snapshot, (shock,))
    greeks = valuation.greeks(snapshot, (shock,))
    pnl = valuation.pnl(snapshot, (shock,))
    assert priced.base_pv == pytest.approx(1_000_000.0)
    assert revalued.pnl < 0.0
    assert greeks["sensitivities"][0]["delta"] != 0.0
    assert "engine_version" in priced.context
    assert "valuation_date" in priced.raw
    assert "curve" in priced.raw
    assert pnl["pnl"] == pytest.approx(revalued.pnl)


def test_risk_api_calculate_exposure_sensitivity_stress_scenario() -> None:
    risk = import_module("3_riskengine.risk")
    snapshot = sample_snapshot()
    shocks = (Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE),)
    exposure = risk.exposure(snapshot)
    sensitivity = risk.sensitivity(snapshot, shocks)
    stress = risk.stress(snapshot, SCENARIOS["gfc_2008"])
    scenario = risk.scenario(snapshot, SCENARIOS["fed_hike_75"])
    calculated = risk.calculate(snapshot, "sensitivity", shocks=shocks)
    assert exposure["analytic"] == "EXPOSURE"
    assert sensitivity["analytic"] == "SENSITIVITY"
    assert stress["analytic"] == "STRESS"
    assert scenario["pnl"] < 0.0
    assert calculated["analytic"] == "SENSITIVITY"
    assert "engine_version" in sensitivity
    assert "ore_adapter" in stress


def test_validation_pricing_greeks_risk_regression_reconciliation() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    shocks = (Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),)
    previous = sample_snapshot(date(2026, 8, 1), equity_value=280_000.0)
    assert engine.validation().pricing().status == "PASS"
    assert engine.validation().greeks(shocks).status == "PASS"
    assert engine.validation().risk(shocks).status == "PASS"
    assert engine.validation().regression(shocks).status == "PASS"
    assert engine.validation().reconciliation(previous).status == "PASS"


def test_financepy_deterministic_sample() -> None:
    adapter = import_module("3_riskengine.adapters.financepy").FinancePyValuationAdapter(
        sample_snapshot().as_of_date
    )
    df = adapter.discount_factor(0.03, 1.0)
    shocked = adapter.shocked_discount_factor(0.03, 0.01, 1.0)
    assert 0.0 < shocked < df < 1.0
    assert adapter.describe()["curve_class"].endswith("FlatDiscountCurve") or "DiscountCurveFlat" in adapter.describe()["curve_class"]


def test_riskfolio_deterministic_sample_initializes() -> None:
    adapter = import_module("3_riskengine.adapters.riskfolio").RiskfolioAdapter()
    probe = adapter.initialize()
    result = adapter.historical_var_cvar([-0.01, 0.002, -0.03, 0.001, 0.0], 0.99)
    assert probe.name == "riskfolio"
    assert result["status"] in {"OK", "INSUFFICIENT_DATA"}
    assert result["engine"] in {"riskfolio", "riskengine_numpy", "riskengine_numpy_fallback"}


def test_ore_adapter_uses_installed_quantlib() -> None:
    adapter = import_module("3_riskengine.adapters.ore").OREAdapter()
    probe = adapter.initialize()
    status = adapter.describe()
    assert probe.name == "ore"
    assert adapter.available is True
    assert probe.error is None
    assert status["quantlib"]["available"] is True
    assert status["quantlib"]["version"]
    assert status["ore_swig"]["available"] is True
    assert status["pricing_backend"] == "ORE"


def test_business_and_router_do_not_import_vendor_packages() -> None:
    router = (ROOT / "2_processing" / "api" / "routers" / "risk_testing.py").read_text(encoding="utf-8")
    service = (ROOT / "4_business" / "risk_testing" / "service.py").read_text(encoding="utf-8")
    assert "import financepy" not in router
    assert "import riskfolio" not in router
    assert "import financepy" not in service
    assert "import riskfolio" not in service


def test_existing_risk_testing_import_path_still_works() -> None:
    adapter = import_module("2_processing.tools.risk_testing.financepy_adapter")
    engine = import_module("2_processing.tools.risk_testing").ProfessionalRiskEngine(sample_snapshot())
    assert adapter.FinancePyValuationAdapter is import_module(
        "3_riskengine.adapters.financepy"
    ).FinancePyValuationAdapter
    assert engine.value()["base_pv"] == pytest.approx(1_000_000.0)


def test_data_quality_is_carried_on_valuation() -> None:
    priced = import_module("3_riskengine.valuation").price(sample_snapshot())
    assert priced.context["data_quality"]["source"] == "test"
    assert priced.raw["data_quality"]["position_count"] == 3


def test_capabilities_contract_from_business_layer() -> None:
    service = import_module("4_business.risk_testing.service")
    payload = service.capabilities_payload(["SENSITIVITY", "XVA"])
    assert payload["module"] == "risk_testing"
    assert payload["financepy_available"] is True
    assert payload["python_modules"]["SENSITIVITY"] == "risk_testing.analytics.sensitivity.run"
    assert payload["time_semantics"]["HISTORICAL_BACKTEST"] == "DATE_RANGE"
    assert "adapters" in payload
