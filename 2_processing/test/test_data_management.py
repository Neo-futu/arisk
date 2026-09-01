"""Unit tests for data-management workbench contracts."""
from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from pydantic import ValidationError

data_management = import_module("2_processing.api.routers.data_management")


def test_position_derives_market_value() -> None:
    payload = data_management.PositionCreate(
        subject_code=" bond-001 ",
        subject_name="Test Bond",
        currency="hkd",
        quantity=Decimal("100"),
        unit_price=Decimal("99.5"),
    )

    assert payload.subject_code == "bond-001"
    assert payload.currency == "HKD"
    assert payload.market_value == Decimal("9950.0")


def test_position_requires_value_or_quantity_and_price() -> None:
    with pytest.raises(ValidationError):
        data_management.PositionCreate(
            subject_code="BOND-001",
            subject_name="Test Bond",
            currency="HKD",
        )


def test_market_quote_rejects_invalid_ohlc() -> None:
    with pytest.raises(ValidationError):
        data_management.MarketQuoteCreate(
            price_date=date(2026, 9, 1),
            security_code="0005.HK",
            market_id="HKEX",
            low_price=Decimal("90"),
            high_price=Decimal("100"),
            close_price=Decimal("101"),
        )


def test_simulated_order_derives_trade_amount() -> None:
    payload = data_management.SimulatedOrderCreate(
        as_of_date=date(2026, 9, 1),
        trade_date=date(2026, 9, 1),
        trade_side="BUY",
        asset_class="bond_corp",
        security_code="bond-001",
        currency="hkd",
        quantity=Decimal("250"),
        price=Decimal("99.25"),
    )

    assert payload.asset_class == "BOND_CORP"
    assert payload.security_code == "BOND-001"
    assert payload.trade_amount == Decimal("24812.50")


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("ALLOW", "VALIDATED"),
        ("ALLOW_WITH_WARNING", "WARNING"),
        ("BLOCK", "BLOCKED"),
        ("UNKNOWN", "BLOCKED"),
    ],
)
def test_simulation_status_mapping(decision: str, expected: str) -> None:
    assert data_management._simulation_status(decision) == expected


def test_portfolio_create_normalizes_and_defaults() -> None:
    payload = data_management.PortfolioCreate(
        port_id=" bhmmf003 ",
        port_name="New MMF",
        port_type="MMF",
        base_currency="hkd",
        inception_date=date(2026, 1, 1),
    )
    assert payload.port_id == "BHMMF003"
    assert payload.base_currency == "HKD"
    assert payload.is_mmf is False  # default


def test_portfolio_create_rejects_invalid_type() -> None:
    with pytest.raises(ValidationError):
        data_management.PortfolioCreate(
            port_id="P1",
            port_name="Bad Type",
            port_type="CRYPTO",  # not in the portfolio_type enum
            inception_date=date(2026, 1, 1),
        )


def test_portfolio_create_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        data_management.PortfolioCreate(port_id="P1", port_name="Missing type/date")


def test_portfolio_create_rejects_bad_port_id() -> None:
    with pytest.raises(ValidationError):
        data_management.PortfolioCreate(
            port_id="1BAD",  # must start with a letter
            port_name="Bad Id",
            port_type="BOND",
            inception_date=date(2026, 1, 1),
        )


def test_portfolio_update_currency_normalized() -> None:
    payload = data_management.PortfolioUpdate(base_currency="usd")
    assert payload.base_currency == "USD"