"""Investment Risk domain → KPI map."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Iterable

MODULE_KPIS: dict[str, tuple[str, ...]] = {
    "overview": ("Gross Exposure", "Net Exposure", "Leverage", "Duration"),
    "exposure": ("Gross Exposure", "Net Exposure", "Factor Exposure"),
    "market_risk": ("VaR", "CVaR", "ES", "Volatility", "Drawdown"),
    "factor_risk": ("Factor Exposure", "Beta", "Tracking Error"),
    "rates_credit": ("Duration", "DV01", "KRD", "CS01"),
    "fx": ("Factor Exposure",),
    "liquidity": ("Liquidity",),
    "concentration": ("Concentration",),
    "counterparty": ("Counterparty Exposure", "PFE", "EPE"),
    "leverage": ("Leverage",),
    "pnl_attribution": ("Risk Contribution",),
    "risk_budget": ("Risk Contribution", "VaR", "Gross Exposure"),
    "macro_dynamics": ("Volatility", "Drawdown", "Beta"),
    "factor_behavior": ("Factor Exposure", "Concentration", "Beta"),
}


def analyze_domain(
    domain: str,
    snapshot: Any,
    *,
    confidence: float = 0.99,
    benchmark_returns: Iterable[float] | None = None,
) -> dict[str, Any]:
    kpis = import_module("3_riskengine.risk.kpis")
    pack: dict[str, Any] = {
        "domain": domain,
        "kpis": kpis.compute_selected(
            snapshot,
            MODULE_KPIS[domain],
            confidence=confidence,
            benchmark_returns=benchmark_returns,
        ),
        "engine": "ARISK RiskEngine",
    }
    if domain in {"liquidity", "counterparty"}:
        bound = import_module("3_riskengine").RiskEngine().bind(snapshot)
        if domain == "liquidity":
            pack["liquidity"] = bound.liquidity().report()
        else:
            pack["counterparty"] = bound.counterparty().report()
    return pack
