"""Phase H: Limit Engine SFC metrics and FinancePy vs ORE cross-engine."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import Shock, RiskFactorType, ShockMode, sample_mmf_snapshot, sample_snapshot


def test_sample_book_stays_green_with_sfc_limits() -> None:
    limits = import_module("3_riskengine.limits")
    report = limits.evaluate(sample_snapshot())
    assert "WAM" in report["limit_ids"]
    assert "WAL" in report["limit_ids"]
    assert report["limits"]["WAM"]["value"] == pytest.approx(0.0)
    assert report["state"] == "GREEN"
    assert report["passed"] is True


def test_mmf_wam_breaches_sfc_sixty() -> None:
    report = import_module("3_riskengine.limits").evaluate(sample_mmf_snapshot())
    assert report["limits"]["WAM"]["value"] == pytest.approx(88.5)
    assert report["limits"]["WAM"]["state"] == "HARD_BREACH"
    assert report["limits"]["WAL"]["value"] == pytest.approx(88.5)
    assert report["limits"]["WAL"]["state"] == "GREEN"
    assert report["passed"] is False


def test_cross_engine_financepy_vs_ore_discount() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_snapshot())
    result = bound.validation().cross_engine()
    assert result.status == "PASS"
    names = {item["name"] for item in result.checks}
    assert "discount_factor_1y" in names
    assert "discount_factor_5y" in names
    assert "ore_app_disabled" in names
    df = next(item for item in result.checks if item["name"] == "discount_factor_5y")
    assert df["relative_error"] <= 1e-3
    packed = bound.validation().run((Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),))
    assert packed.status == "PASS"


def test_governance_includes_cross_engine_and_mmf() -> None:
    mixed = import_module("3_riskengine").RiskEngine().bind(sample_snapshot()).governance().review()
    mmf = import_module("3_riskengine").RiskEngine().bind(sample_mmf_snapshot()).governance().review()
    assert mixed["passed"] is True
    assert mixed["validation"]["status"] == "PASS"
    assert mixed["mmf"]["is_mmf"] is False
    assert mmf["mmf"]["is_mmf"] is True
    assert mmf["mmf"]["status"] == "breach"
    assert mmf["passed"] is False
    assert mmf["is_trade_instruction"] is False
