"""Compatibility facades for 2_processing.tools.

Wave 2 does not move algorithms. Callers that want a stable name can load
legacy modules through this registry; the files under tools/ stay authoritative.

    Old:  2_processing.tools.*
      ↓
    Compatibility: 2_processing.compatibility.legacy_tools.load(...)
      ↓
    New:  3_riskengine / 4_business  (later Waves)
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType

LEGACY_MODULES: dict[str, str] = {
    "risk_testing": "2_processing.tools.risk_testing",
    "exposure_engine": "2_processing.tools.risk.exposure_engine",
    "var_calculator": "2_processing.tools.risk.var_calculator",
    "portfolio_optimizer": "2_processing.tools.performance.portfolio_optimizer",
    "investment_analysis": "2_processing.tools.performance.investment_analysis",
    "attribution": "2_processing.tools.performance.attribution",
}


TARGET_ALIASES: dict[str, str] = {
    "4_business.risk_testing.engine": "4_business.risk_testing.service",
    "4_business.portfolio_optimization.optimizer": "4_business.portfolio_optimization.service",
    "4_business.investment_risk.analysis": "2_processing.tools.performance.investment_analysis",
    "3_riskengine.risk.exposure": "2_processing.tools.risk.exposure_engine",
    "3_riskengine.risk.var": "2_processing.tools.risk.var_calculator",
    "4_business.risk_governance.service": "4_business.risk_governance.service",
    "3_riskengine.limits.engine": "3_riskengine.limits",
    "5_integrations.quant": "5_integrations.quant",
    "7_ai.runtime": "7_ai.runtime",
}


def load(name: str) -> ModuleType:
    """Import a still-authoritative legacy tools module by registry name."""
    try:
        module_path = LEGACY_MODULES[name]
    except KeyError as exc:
        known = ", ".join(sorted(LEGACY_MODULES))
        raise KeyError(f"Unknown legacy tool {name!r}. Known: {known}") from exc
    return import_module(module_path)


def load_target(target_name: str) -> ModuleType:
    """Resolve a Target-oriented name to the Current module that still owns it."""
    try:
        module_path = TARGET_ALIASES[target_name]
    except KeyError as exc:
        known = ", ".join(sorted(TARGET_ALIASES))
        raise KeyError(f"Unknown target alias {target_name!r}. Known: {known}") from exc
    return import_module(module_path)


__all__ = ["LEGACY_MODULES", "TARGET_ALIASES", "load", "load_target"]
