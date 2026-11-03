"""REPO (FinancePy) + STRUCTURED (ORE) product coverage."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import Shock, RiskFactorType, ShockMode, sample_repo_structured_snapshot


def test_repo_and_structured_assemble_and_route() -> None:
    products = import_module("3_riskengine.products")
    engine = import_module("3_riskengine").RiskEngine()
    snapshot = sample_repo_structured_snapshot()
    lines = products.products_from_snapshot(snapshot)
    assert [item.kind.value for item in lines] == ["REPO", "STRUCTURED"]
    assert isinstance(lines[0], products.Repo)
    assert isinstance(lines[1], products.StructuredNote)
    assert engine.resolve(lines[0], "PRICE").adapter == "financepy"
    assert engine.resolve(lines[0], "PRICE").model == "repo_carry"
    assert engine.resolve(lines[1], "PRICE").adapter == "ore"
    assert engine.resolve(lines[1], "PRICE").model == "scripted_or_otc"
    assert engine.resolve(lines[1], "GREEKS").adapter == "ore"


def test_repo_structured_zero_shock_and_factor_pnl() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_repo_structured_snapshot())
    priced = bound.valuation().price()
    assert priced.base_pv == pytest.approx(250_000.0, abs=1e-4)
    by_code = {row["security_code"]: row for row in priced.trade_values}
    assert by_code["REPO7D"]["engine"] == "financepy"
    assert by_code["STRUCT1"]["engine"] == "ore"

    rate = bound.valuation().revalue((Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE),))
    equity = bound.valuation().revalue((Shock(RiskFactorType.EQUITY, -0.05, ShockMode.RELATIVE),))
    vol = bound.valuation().revalue((Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE),))
    assert rate.pnl != 0.0
    assert equity.pnl != 0.0
    assert vol.pnl != 0.0
    repo_row = next(row for row in rate.trade_values if row["security_code"] == "REPO7D")
    struct_eq = next(row for row in equity.trade_values if row["security_code"] == "STRUCT1")
    assert repo_row["pnl"] < 0.0
    assert struct_eq["pnl"] < 0.0


def test_adapters_status_lists_three_vendors() -> None:
    status = import_module("3_riskengine").RiskEngine().adapters_status()
    assert status["financepy"]["available"] is True
    assert status["riskfolio"]["available"] is True
    assert status["ore"]["available"] is True
    mapping = import_module("3_riskengine").RiskEngine().ore.map_snapshot(sample_repo_structured_snapshot())
    types = {row["id"]: row["type"] for row in mapping["trades"]}
    assert types["REPO7D"] == "Repo"
    assert types["STRUCT1"] == "ScriptedTrade"
