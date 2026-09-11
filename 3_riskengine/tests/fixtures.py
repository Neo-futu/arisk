"""Deterministic fixtures for RiskEngine tests. Uses in-memory snapshots only."""
from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module

models = import_module("2_processing.tools.risk_testing.models")
PortfolioSnapshot = models.PortfolioSnapshot
Position = models.Position
RiskFactorType = models.RiskFactorType
Shock = models.Shock
ShockMode = models.ShockMode
SCENARIOS = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS


def sample_snapshot(as_of: date = date(2026, 9, 1), equity_value: float = 300_000.0):
    returns = []
    for index in range(300):
        value = ((index % 17) - 8) * 0.00035
        if index in {90, 180, 270}:
            value = -0.025
        returns.append((as_of - timedelta(days=299 - index), value))
    return PortfolioSnapshot(
        fund_id="TEST001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[
            Position(
                security_code="BOND5Y",
                security_name="Five Year Bond",
                asset_class="BOND",
                currency="HKD",
                market_value=600_000.0,
                market_value_base=600_000.0,
                duration=4.5,
                convexity=20.0,
                ytm=0.035,
                coupon_rate=0.03,
                maturity_date=as_of + timedelta(days=365 * 5),
            ),
            Position(
                security_code="US_EQ",
                security_name="US Equity",
                asset_class="EQUITY",
                currency="USD",
                market_value=equity_value / 7.8,
                market_value_base=equity_value,
                fx_rate=7.8,
            ),
            Position(
                security_code="CASH",
                security_name="Cash",
                asset_class="CASH",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
            ),
        ],
        nav_returns=returns,
        data_quality={"position_count": 3, "source": "test"},
    )


def sample_mmf_snapshot(as_of: date = date(2026, 9, 1)):
    """Look-through MMF book: bond + CD + deposit + cash."""

    return PortfolioSnapshot(
        fund_id="BHMMF001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=1_000_000.0,
        positions=[
            Position(
                security_code="TBILL90",
                security_name="T-Bill 90D",
                asset_class="BOND",
                currency="HKD",
                market_value=400_000.0,
                market_value_base=400_000.0,
                duration=0.20,
                ytm=0.04,
                coupon_rate=0.0,
                maturity_date=as_of + timedelta(days=90),
                metadata={"issuer": "HKMA", "rating": "AAA"},
            ),
            Position(
                security_code="CD180",
                security_name="Bank CD 180D",
                asset_class="CD",
                currency="HKD",
                market_value=250_000.0,
                market_value_base=250_000.0,
                duration=0.49,
                ytm=0.035,
                coupon_rate=0.035,
                maturity_date=as_of + timedelta(days=180),
                metadata={"issuer": "Bank A", "rating": "A"},
            ),
            Position(
                security_code="DEP30",
                security_name="Call Deposit",
                asset_class="DEPOSIT",
                currency="HKD",
                market_value=250_000.0,
                market_value_base=250_000.0,
                duration=30 / 365,
                ytm=0.03,
                coupon_rate=0.03,
                maturity_date=as_of + timedelta(days=30),
                metadata={"issuer": "Bank B", "rating": "A"},
            ),
            Position(
                security_code="CASH",
                security_name="Cash",
                asset_class="CASH",
                currency="HKD",
                market_value=100_000.0,
                market_value_base=100_000.0,
            ),
        ],
        nav_returns=[],
        data_quality={"position_count": 4, "source": "test", "port_type": "MMF"},
    )


def sample_otc_snapshot(as_of: date = date(2026, 9, 1)):
    """FX / listed / rates / credit book for ORE product tests."""

    maturity_1y = as_of + timedelta(days=365)
    maturity_5y = as_of + timedelta(days=365 * 5)
    return PortfolioSnapshot(
        fund_id="OTC001",
        as_of_date=as_of,
        reporting_currency="HKD",
        net_asset=300_000.0,
        positions=[
            Position(
                security_code="FXSPOT",
                security_name="USD Spot",
                asset_class="FX",
                currency="USD",
                market_value=12_820.51,
                market_value_base=100_000.0,
                fx_rate=7.8,
                metadata={"pair": "USDHKD", "spot": 7.8, "counterparty": "BANKFX"},
            ),
            Position(
                security_code="FXFWD",
                security_name="EURUSD Forward 1Y",
                asset_class="FX_FORWARD",
                currency="USD",
                market_value=100_000.0,
                market_value_base=100_000.0,
                fx_rate=7.8,
                duration=1.0,
                maturity_date=maturity_1y,
                metadata={
                    "pair": "EURUSD",
                    "spot": 1.08,
                    "strike": 1.08,
                    "notional": 100_000.0,
                    "counterparty": "BANKFX",
                },
            ),
            Position(
                security_code="FXOPT",
                security_name="EURUSD Call 6M",
                asset_class="FX_OPTION",
                currency="USD",
                market_value=5_000.0,
                market_value_base=5_000.0,
                duration=0.5,
                maturity_date=as_of + timedelta(days=182),
                metadata={
                    "pair": "EURUSD",
                    "spot": 1.08,
                    "strike": 1.08,
                    "volatility": 0.10,
                    "option_type": "Call",
                    "exercise": "European",
                    "notional": 100_000.0,
                    "domestic_rate": 0.045,
                    "foreign_rate": 0.03,
                    "counterparty": "BANKFX",
                },
            ),
            Position(
                security_code="EQFUT",
                security_name="Equity Future",
                asset_class="FUTURE",
                currency="USD",
                market_value=50_000.0,
                market_value_base=50_000.0,
                duration=0.25,
                maturity_date=as_of + timedelta(days=90),
                metadata={"spot": 100.0, "underlying": "EQUITY", "notional": 50_000.0},
            ),
            Position(
                security_code="EQOPT",
                security_name="Equity Call",
                asset_class="OPTION",
                currency="USD",
                market_value=8_000.0,
                market_value_base=8_000.0,
                duration=0.5,
                maturity_date=as_of + timedelta(days=182),
                metadata={
                    "spot": 100.0,
                    "strike": 100.0,
                    "volatility": 0.20,
                    "option_type": "Call",
                    "exercise": "European",
                    "notional": 100.0,
                },
            ),
            Position(
                security_code="IRS5Y",
                security_name="USD IRS 5Y",
                asset_class="IRS",
                currency="USD",
                market_value=2_000.0,
                market_value_base=2_000.0,
                duration=4.5,
                ytm=0.03,
                maturity_date=maturity_5y,
                metadata={"notional": 1_000_000.0, "strike": 0.03, "pay_fixed": True, "tenor_years": 5.0, "counterparty": "BANKIR"},
            ),
            Position(
                security_code="SWPT",
                security_name="1y5y Payer Swaption",
                asset_class="SWAPTION",
                currency="USD",
                market_value=15_000.0,
                market_value_base=15_000.0,
                duration=5.0,
                maturity_date=maturity_5y,
                metadata={
                    "notional": 1_000_000.0,
                    "strike": 0.03,
                    "volatility": 0.20,
                    "pay_fixed": True,
                    "tenor_years": 5.0,
                    "option_tenor_years": 1.0,
                    "counterparty": "BANKIR",
                },
            ),
            Position(
                security_code="CDS5Y",
                security_name="5Y CDS",
                asset_class="CDS",
                currency="USD",
                market_value=20_000.0,
                market_value_base=20_000.0,
                duration=5.0,
                maturity_date=maturity_5y,
                metadata={
                    "notional": 1_000_000.0,
                    "strike": 0.01,
                    "hazard_rate": 0.01,
                    "recovery_rate": 0.40,
                    "protection_seller": False,
                    "tenor_years": 5.0,
                    "counterparty": "BANKCD",
                },
            ),
        ],
        nav_returns=[],
        data_quality={"position_count": 8, "source": "test", "port_type": "OTC"},
    )
