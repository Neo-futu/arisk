"""Unit tests for indicator-explorer pure logic (no DB)."""
from datetime import date
from importlib import import_module

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

indicators = import_module("2_processing.api.routers.indicators")


def test_resolve_range_explicit() -> None:
    start, end = indicators._resolve_range(None, date(2020, 1, 1), date(2021, 1, 1), None)
    assert start == date(2020, 1, 1)
    assert end == date(2021, 1, 1)


def test_resolve_range_explicit_inverted_rejected() -> None:
    with pytest.raises(HTTPException):
        indicators._resolve_range(None, date(2022, 1, 1), date(2021, 1, 1), None)


def test_resolve_range_period_anchored_on_latest() -> None:
    latest = date(2026, 8, 1)
    start, end = indicators._resolve_range("1Y", None, None, latest)
    assert end == latest
    assert start == date(2025, 8, 1)


def test_resolve_range_max_uses_wide_floor() -> None:
    latest = date(2026, 8, 1)
    start, end = indicators._resolve_range("MAX", None, None, latest)
    assert start == date(1900, 1, 1)
    assert end == latest


def test_resolve_range_default_period_when_missing() -> None:
    latest = date(2026, 8, 1)
    start, end = indicators._resolve_range(None, None, None, latest)
    # Defaults to a 3Y window.
    assert start == date(2023, 8, 1)
    assert end == latest


def test_parse_ids_dedup_and_upper() -> None:
    assert indicators._parse_ids("hk_cpi_yoy, us_cpi_yoy , hk_cpi_yoy") == ["HK_CPI_YOY", "US_CPI_YOY"]


def test_parse_ids_empty_rejected() -> None:
    with pytest.raises(HTTPException):
        indicators._parse_ids("  , ")


def test_parse_ids_over_limit_rejected() -> None:
    many = ",".join(f"IND_{i}" for i in range(indicators.MAX_COMPARE + 1))
    with pytest.raises(HTTPException):
        indicators._parse_ids(many)


def test_indicator_def_normalizes_id_and_country() -> None:
    payload = indicators.IndicatorDefCreate(
        indicator_id=" hk_new ",
        indicator_name="Test",
        category="通脹",
        country="hk",
        unit="%",
    )
    assert payload.indicator_id == "HK_NEW"
    assert payload.country == "HK"
    assert payload.frequency == "MONTHLY"


def test_indicator_def_rejects_bad_id() -> None:
    with pytest.raises(ValidationError):
        indicators.IndicatorDefCreate(
            indicator_id="1bad",
            indicator_name="Test",
            category="通脹",
            country="HK",
            unit="%",
        )
