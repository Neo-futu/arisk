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
    if domain in {
        "overview",
        "exposure",
        "liquidity",
        "counterparty",
        "factor_risk",
        "factor_behavior",
        "pnl_attribution",
        "rates_credit",
        "risk_budget",
    }:
        bound = import_module("3_riskengine").RiskEngine().bind(snapshot)
        if domain == "overview":
            pack["overview"] = bound.portfolio().overview()
        elif domain == "exposure":
            # 整体风险敞口页：基本信息 + 风险指标 Tab（核心五卡 / VaR / 六大风控类型）
            pack["basic_info"] = bound.portfolio().basic_info()
            pack["risk_indicators"] = bound.portfolio().risk_indicators()
        elif domain == "pnl_attribution":
            pack["attribution"] = bound.pnl().attribution()
        elif domain == "rates_credit":
            pack["rates_credit"] = bound.risk().rates_credit()
        elif domain == "liquidity":
            # 产品压力测试 Tab（Bloomberg LQAP）+ 通用流动性报告
            pack["product_stress"] = bound.liquidity().product_stress()
            pack["liquidity"] = bound.liquidity().report()
        elif domain == "counterparty":
            pack["counterparty"] = bound.counterparty().report()
        elif domain == "factor_risk":
            pack["factor_risk"] = bound.risk().factor_risk(
                meta={"benchmark_returns": list(benchmark_returns or [])},
                confidence=confidence,
            )
            pack["portfolio_factor"] = pack["factor_risk"].get("factor_risk")
        elif domain == "factor_behavior":
            pack["factor_behavior"] = bound.risk().factor_behavior()
        elif domain == "risk_budget":
            pack["pretrade_budget"] = bound.risk().pretrade_budget(confidence=confidence)
            pack["risk_budget"] = pack["pretrade_budget"]
        else:
            pack["portfolio_factor"] = bound.portfolio().risk(confidence=confidence)
    return pack
