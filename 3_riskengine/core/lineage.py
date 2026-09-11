"""RiskEngine identity and report lineage."""
from __future__ import annotations

RISKENGINE_VERSION = "1.0.0"
RISKENGINE_NAME = "ARISK RiskEngine"

DEFAULT_ASSUMPTIONS = (
    "Fixed-income repricing uses FinancePy FlatDiscountCurve cash-flow discounting with legacy DiscountCurveFlat compatibility.",
    "XVA discounting and hazard survival use ORE-SWIG (preferred) or QuantLib FlatForward / FlatHazardRate when installed.",
    "MMF is a first-class product: NAV is the share-class view; WAM/WAL and rate sensitivity use look-through holdings.",
    "Unified valuation uses Product + Market + Model; Bond/Deposit/CD discounting is FinancePy FlatDiscountCurve via the adapter.",
    "OTC FX / IRS / Swaption / CDS / listed options are priced through the ORE-SWIG adapter (no OREApp XML); zero-shock PV stays platform market value.",
    "Portfolio Risk aggregates look-through product PVs; Fund Risk is the share-class NAV view. VaR/CVaR/RC/optimization go through the Riskfolio adapter.",
    "Risk Testing (sensitivity, stress, scenario, reverse stress, KRD) revalues through Product + Market + Model; tail/VaR backtest use Riskfolio; XVA uses ORE trade mapping without OREApp XML.",
    "Liquidity and counterparty are computed per product then aggregated; MMF redemption uses a liquidity waterfall; SFC WAM 60 / WAL 120 / 50bp shadow 口径 lives in RiskEngine.",
    "Cross-engine validation compares FinancePy FlatDiscountCurve DF with ORE FlatForward DF; it does not construct bond, swaption or CDS instrument objects.",
    "Existing ARISK portfolio and market data are authoritative inputs.",
    "Results are risk estimates, not accounting valuations or regulatory capital approval.",
)
