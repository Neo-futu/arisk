"""Unified facade for modularized investment analysis functions."""
from __future__ import annotations

from .investment_analysis_attribution import compute_performance_attribution
from .investment_analysis_model_attribution import compute_model_attribution, list_attribution_benchmarks
from .investment_analysis_basic_info import compute_portfolio_basic_info
from .investment_analysis_exposure_report import read_reported_exposure
from .investment_analysis_factor import compute_factor_behavior_risk, compute_factor_risk
from .investment_analysis_holdings import compute_security_holdings
from .investment_analysis_liquidity_stress import compute_liquidity_stress_testing
from .investment_analysis_macro import compute_macro_market_dynamics
from .investment_analysis_metric_board import compute_risk_metric_board
from .investment_analysis_overview import compute_portfolio_overview
from .investment_analysis_pretrade import compute_pretrade_risk_budget
from .investment_analysis_rates_credit import compute_rates_credit_sensitivity
from .investment_analysis_risk_indicators import compute_risk_indicators
from .investment_analysis_timeseries import (
    compute_performance_attribution_timeseries,
    compute_portfolio_overview_timeseries,
    compute_risk_indicator_timeseries,
)

__all__ = [
    "compute_portfolio_overview",
    "compute_portfolio_basic_info",
    "compute_security_holdings",
    "compute_risk_indicators",
    "compute_performance_attribution",
    "compute_model_attribution",
    "list_attribution_benchmarks",
    "compute_rates_credit_sensitivity",
    "compute_liquidity_stress_testing",
    "compute_pretrade_risk_budget",
    "compute_macro_market_dynamics",
    "compute_factor_behavior_risk",
    "compute_factor_risk",
    "compute_portfolio_overview_timeseries",
    "compute_risk_indicator_timeseries",
    "compute_performance_attribution_timeseries",
    "compute_risk_metric_board",
    "read_reported_exposure",
]
