"""Phase G: liquidity and counterparty per product, then aggregate."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import sample_mmf_snapshot, sample_otc_snapshot, sample_snapshot


def _bound(snapshot=None):
    return import_module("3_riskengine").RiskEngine().bind(snapshot or sample_snapshot())


def test_liquidity_buckets_and_redemption() -> None:
    bound = _bound()
    report = bound.liquidity().report(20.0)
    buckets = report["buckets"]
    assert report["analytic"] == "LIQUIDITY"
    assert buckets["T0"]["base_pv"] == pytest.approx(100_000.0)
    assert buckets["1W"]["base_pv"] == pytest.approx(300_000.0)
    assert buckets["ILLIQUID"]["base_pv"] == pytest.approx(600_000.0)
    assert report["redemption"]["covered"] is True
    assert report["ore_app"] is False
    ratio = bound.liquidity().ratio()
    assert ratio["kpi"] == "Liquidity"
    assert ratio["result"]["pct_nav"] == pytest.approx(10.0)


def test_mmf_redemption_uses_look_through_buckets() -> None:
    bound = _bound(sample_mmf_snapshot())
    cover = bound.liquidity().redemption(20.0)
    assert cover["analytic"] == "REDEMPTION"
    assert cover["covered"] is True
    assert cover["shortfall"] == pytest.approx(0.0)
    assert bound.liquidity().buckets()["buckets"]["T0"]["base_pv"] == pytest.approx(100_000.0)


def test_counterparty_xva_allocated_by_product() -> None:
    bound = _bound()
    xva = bound.counterparty().xva()
    report = bound.counterparty().report()
    assert report["analytic"] == "COUNTERPARTY"
    assert report["ore_app"] is False
    assert report["cva"] == pytest.approx(xva["cva"])
    assert set(row["security_code"] for row in report["positions"]) == {"BOND5Y", "US_EQ", "CASH"}
    allocated = sum(item["cva"] for item in report["positions"])
    assert allocated == pytest.approx(report["cva"])
    assert report["by_counterparty"]
    otc = _bound(sample_otc_snapshot()).counterparty().report()
    assert "BANKIR" in otc["by_counterparty"] or otc["positions"]
    assert otc["ore_app"] is False
