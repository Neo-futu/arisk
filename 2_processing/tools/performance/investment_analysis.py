"""Backward-compatible module entry for investment analysis."""
from __future__ import annotations

from .investanalsis import (
    compute_factor_behavior_risk,
    compute_liquidity_stress_testing,
    compute_macro_market_dynamics,
    compute_performance_attribution,
    compute_performance_attribution_timeseries,
    compute_portfolio_basic_info,
    compute_portfolio_overview,
    compute_portfolio_overview_timeseries,
    compute_pretrade_risk_budget,
    compute_rates_credit_sensitivity,
    compute_risk_indicator_timeseries,
    compute_risk_indicators,
    compute_risk_metric_board,
    compute_security_holdings,
    read_reported_exposure,
)
from .investment_analysis_common import (
    _beta,
    _daily_returns,
    _performance_periods,
    _return_between,
)

__all__ = [
    "_beta",
    "_daily_returns",
    "_performance_periods",
    "_return_between",
    "compute_portfolio_overview",
    "compute_portfolio_basic_info",
    "compute_security_holdings",
    "compute_risk_indicators",
    "compute_performance_attribution",
    "compute_portfolio_overview_timeseries",
    "compute_risk_indicator_timeseries",
    "compute_performance_attribution_timeseries",
    "compute_rates_credit_sensitivity",
    "compute_liquidity_stress_testing",
    "compute_pretrade_risk_budget",
    "compute_macro_market_dynamics",
    "compute_factor_behavior_risk",
    "compute_risk_metric_board",
    "read_reported_exposure",
]
