"""Unit tests for portfolio cockpit compliance-status logic (no DB)."""
from importlib import import_module

cockpit = import_module("2_processing.api.routers.portfolio_cockpit")
status = cockpit._compliance_status


def test_non_mmf_always_ok() -> None:
    # Non-MMF has no WAM/WAL/deviation constraints even with wild inputs.
    assert status(False, 999, 999, 60, 120, 999) == "ok"


def test_mmf_within_limits_ok() -> None:
    assert status(True, 52, 68, 60, 120, 12.5) == "ok"


def test_wam_breach() -> None:
    assert status(True, 61, 68, 60, 120, 0) == "breach"


def test_wal_breach() -> None:
    assert status(True, 50, 121, 60, 120, 0) == "breach"


def test_deviation_breach_above_50bp() -> None:
    assert status(True, 50, 100, 60, 120, 51) == "breach"
    assert status(True, 50, 100, 60, 120, -55) == "breach"


def test_wam_warn_near_limit() -> None:
    # 90% of 60 = 54 → 55 warns, not breach.
    assert status(True, 55, 68, 60, 120, 0) == "warn"


def test_deviation_warn_between_40_and_50bp() -> None:
    assert status(True, 50, 100, 60, 120, 45) == "warn"


def test_breach_takes_precedence_over_warn() -> None:
    # WAM warns but WAL breaches → breach wins.
    assert status(True, 55, 121, 60, 120, 0) == "breach"


def test_missing_metrics_ok() -> None:
    assert status(True, None, None, 60, 120, None) == "ok"
