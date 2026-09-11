"""Wave 2 skeleton import smoke tests — ensure packages are importable."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RISKENGINE_MODULES = [
    "3_riskengine",
    "3_riskengine.core",
    "3_riskengine.adapters",
    "3_riskengine.valuation",
    "3_riskengine.instruments",
    "3_riskengine.market",
    "3_riskengine.risk",
    "3_riskengine.risk.kpis",
    "3_riskengine.stress",
    "3_riskengine.scenario",
    "3_riskengine.liquidity",
    "3_riskengine.counterparty",
    "3_riskengine.pnl",
    "3_riskengine.limits",
    "3_riskengine.validation",
    "3_riskengine.utils",
    "3_riskengine.models",
    "3_riskengine.products",
    "3_riskengine.products.money_market",
    "3_riskengine.portfolio",
    "3_riskengine.trade",
    "3_riskengine.core.resolve",
    "3_riskengine.products.assemble",
    "3_riskengine.models.catalog",
    "3_riskengine.valuation.pipeline",
    "3_riskengine.adapters.ore.trade",
    "3_riskengine.adapters.ore.pricing",
    "3_riskengine.trade.build",
    "3_riskengine.products.fx",
    "3_riskengine.portfolio.aggregate",
    "3_riskengine.portfolio.api",
    "3_riskengine.risk.testing",
    "3_riskengine.governance",
    "3_riskengine.liquidity.buckets",
    "3_riskengine.limits.sfc",
    "3_riskengine.validation.cross_engine",
    "3_riskengine.counterparty.aggregate",
]

BUSINESS_MODULES = [
    "4_business",
    "4_business.investment_risk",
    "4_business.investment_risk.overview",
    "4_business.investment_risk.market_risk",
    "4_business.portfolio_optimization",
    "4_business.portfolio_optimization.construction",
    "4_business.portfolio_optimization.hrp",
    "4_business.portfolio_optimization.simulation",
    "4_business.risk_testing",
    "4_business.risk_governance",
    "4_business.risk_governance.policy",
    "4_business.portfolio_management",
    "4_business.trading",
    "4_business.operations",
]

AI_MODULES = [
    "7_ai",
    "7_ai.runtime",
    "7_ai.agents",
    "7_ai.agents.investment_agent",
    "7_ai.agents.portfolio_agent",
    "7_ai.agents.risk_agent",
    "7_ai.agents.valuation_agent",
    "7_ai.agents.workflow_agent",
    "7_ai.skills",
    "7_ai.tools",
    "7_ai.tools.mcp_layer",
    "7_ai.workflows",
    "7_ai.knowledge",
]

COMPAT_MODULES = [
    "legacy",
    "legacy.paths",
    "adapter",
    "2_processing.compatibility",
    "2_processing.compatibility.legacy_tools",
    "4_business.risk_testing.compat",
    "4_business.investment_risk.compat",
    "4_business.portfolio_optimization.compat",
    "4_business.risk_governance.compat",
]

INTEGRATION_MODULES = [
    "5_integrations",
    "5_integrations.market_data",
    "5_integrations.pms",
    "5_integrations.oms",
    "5_integrations.ems",
    "5_integrations.broker",
    "5_integrations.custodian",
    "5_integrations.fund_admin",
    "5_integrations.accounting",
    "5_integrations.quant",
]


@pytest.mark.parametrize("module_name", RISKENGINE_MODULES + BUSINESS_MODULES + AI_MODULES + COMPAT_MODULES + INTEGRATION_MODULES)
def test_wave2_skeleton_importable(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_legacy_tools_registry_does_not_move_files() -> None:
    compat = importlib.import_module("2_processing.compatibility")
    assert "risk_testing" in compat.LEGACY_MODULES
    assert compat.LEGACY_MODULES["risk_testing"] == "2_processing.tools.risk_testing"


def test_old_risk_testing_import_still_works() -> None:
    mod = importlib.import_module("2_processing.tools.risk_testing")
    assert hasattr(mod, "ProfessionalRiskEngine")


def test_compatibility_load_risk_testing() -> None:
    load = importlib.import_module("2_processing.compatibility").load
    mod = load("risk_testing")
    assert mod.ProfessionalRiskEngine is importlib.import_module("2_processing.tools.risk_testing").ProfessionalRiskEngine


def test_business_compat_resolves_current_engine() -> None:
    current_engine = importlib.import_module("4_business.risk_testing").current_engine
    assert current_engine() is importlib.import_module("2_processing.tools.risk_testing")
