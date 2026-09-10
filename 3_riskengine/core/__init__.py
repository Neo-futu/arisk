"""3_riskengine.core — unified engine, contracts and lineage."""

from .contracts import (
    AnalyticKind,
    Instrument,
    Market,
    MarketSnapshot,
    Model,
    Portfolio,
    PortfolioKind,
    Position,
    Product,
    ProductKind,
    RESULT_LINEAGE_KEYS,
    RiskFactor,
    RiskResult,
    Scenario,
    Shock,
    ShockMode,
    StressResult,
    Trade,
    ValidationResult,
    ValuationContext,
    ValuationResult,
    ViewMode,
)
from .lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .resolve import EngineRef, resolve

__all__ = [
    "AnalyticKind",
    "BoundRiskEngine",
    "EngineRef",
    "Instrument",
    "Market",
    "MarketSnapshot",
    "Model",
    "Portfolio",
    "PortfolioKind",
    "Position",
    "Product",
    "ProductKind",
    "RESULT_LINEAGE_KEYS",
    "RISKENGINE_NAME",
    "RISKENGINE_VERSION",
    "RevaluationKernel",
    "RiskEngine",
    "RiskFactor",
    "RiskResult",
    "Scenario",
    "Shock",
    "ShockMode",
    "StressResult",
    "Trade",
    "ValidationResult",
    "ValuationContext",
    "ValuationResult",
    "ViewMode",
    "resolve",
]


def __getattr__(name: str):
    if name in {"BoundRiskEngine", "RiskEngine"}:
        from .engine import BoundRiskEngine, RiskEngine

        return RiskEngine if name == "RiskEngine" else BoundRiskEngine
    if name == "RevaluationKernel":
        from .kernel import RevaluationKernel

        return RevaluationKernel
    raise AttributeError(name)
