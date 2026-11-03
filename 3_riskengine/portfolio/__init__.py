"""Portfolio aggregation objects. Master data remains fsi.para_portfolio / fsi.balance_*."""

from ..core.contracts import Portfolio, PortfolioKind, Position
from .aggregate import aggregate
from .api import PortfolioAPI
from .cockpit import (
    BUSINESS_MODULES as COCKPIT_MODULES,
    CHART_IDS,
    TABLE_COLUMNS,
    charts_payload,
    fundamentals,
    normalize_http_overview,
    overview_from_rows,
    period_return,
    verify_business_modules as verify_cockpit_modules,
    verify_overview_contract,
)
from .measures import fund_risk, optimize_book, portfolio_risk
from .overview import (
    BUSINESS_MODULES as OVERVIEW_MODULES,
    fundamentals as overview_fundamentals,
    verify_business_modules as verify_overview_modules,
)
from .basic_info import (
    BUSINESS_MODULES as BASIC_INFO_MODULES,
    fundamentals as basic_info_fundamentals,
    verify_business_modules as verify_basic_info_modules,
)
from .risk_indicators import (
    BUSINESS_MODULES as RISK_INDICATOR_MODULES,
    REQUIRED_METRIC_IDS,
    RISK_CATEGORIES,
    fundamentals as risk_indicators_fundamentals,
    verify_business_modules as verify_risk_indicator_modules,
)
from .optimization import (
    BUSINESS_MODULES as PORTFOLIO_OPT_MODULES,
    fundamentals as portfolio_opt_fundamentals,
    verify_business_modules as verify_portfolio_opt_modules,
)

__all__ = [
    "BASIC_INFO_MODULES",
    "CHART_IDS",
    "COCKPIT_MODULES",
    "OVERVIEW_MODULES",
    "PORTFOLIO_OPT_MODULES",
    "REQUIRED_METRIC_IDS",
    "RISK_CATEGORIES",
    "RISK_INDICATOR_MODULES",
    "Portfolio",
    "PortfolioAPI",
    "PortfolioKind",
    "Position",
    "TABLE_COLUMNS",
    "aggregate",
    "basic_info_fundamentals",
    "charts_payload",
    "fund_risk",
    "fundamentals",
    "normalize_http_overview",
    "optimize_book",
    "overview_from_rows",
    "overview_fundamentals",
    "period_return",
    "portfolio_opt_fundamentals",
    "portfolio_risk",
    "risk_indicators_fundamentals",
    "verify_basic_info_modules",
    "verify_cockpit_modules",
    "verify_overview_contract",
    "verify_overview_modules",
    "verify_portfolio_opt_modules",
    "verify_risk_indicator_modules",
]
