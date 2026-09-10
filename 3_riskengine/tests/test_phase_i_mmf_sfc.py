"""Phase I: MMF WAM/WAL and SFC cockpit 口径 reconciliation."""
from __future__ import annotations

from importlib import import_module

import pytest

from .fixtures import sample_mmf_snapshot, sample_snapshot


def test_engine_mmf_sfc_matches_cockpit_status_function() -> None:
    bound = import_module("3_riskengine").RiskEngine().bind(sample_mmf_snapshot())
    engine = bound.liquidity().mmf()
    cockpit = import_module("2_processing.api.routers.portfolio_cockpit")
    status = cockpit._compliance_status(
        True,
        engine["wam_days"],
        engine["wal_days"],
        engine["wam_limit"],
        engine["wal_limit"],
        engine["shadow_deviation_bp"],
    )
    assert engine["analytic"] == "MMF_SFC"
    assert engine["wam_days"] == pytest.approx(88.5)
    assert engine["wal_days"] == pytest.approx(88.5)
    assert engine["wam_limit"] == pytest.approx(60.0)
    assert engine["wal_limit"] == pytest.approx(120.0)
    assert engine["status"] == "breach"
    assert status == "breach"
    aligned = import_module("3_riskengine.liquidity.mmf").reconcile(engine, engine)
    assert aligned["aligned"] is True


def test_non_mmf_cockpit_ok() -> None:
    engine = import_module("3_riskengine").RiskEngine().bind(sample_snapshot()).liquidity().mmf()
    assert engine["is_mmf"] is False
    assert engine["status"] == "ok"
    cockpit = import_module("2_processing.api.routers.portfolio_cockpit")
    assert cockpit._compliance_status(False, 999, 999, 60, 120, 999) == "ok"
    assert cockpit.DEVIATION_BREACH_BP == 50.0
