"""Wave 5 portfolio optimization: Riskfolio adapter, gates, simulation, persistence."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from .fixtures import sample_snapshot

ROOT = Path(__file__).resolve().parents[2]
OPTIMIZERS = import_module("4_business.portfolio_optimization.domains").OPTIMIZERS


def _returns(tickers: list[str] | None = None):
    service = import_module("4_business.portfolio_optimization.service")
    return service.synthetic_returns(tickers or ["AAA", "BBB", "CCC", "CASH"], 360)


def test_catalog_lists_modules_and_gate() -> None:
    catalog = import_module("4_business.portfolio_optimization.service").catalog()
    assert catalog["frontend_routes"] == "/portfolio-opt"
    assert catalog["primary_adapter"] == "riskfolio"
    assert catalog["is_trade_instruction"] is False
    assert set(catalog["methods"]) == set(OPTIMIZERS)
    assert catalog["gate"] == [
        "optimization",
        "riskengine",
        "valuation",
        "investment_risk",
        "risk_testing",
        "limits",
    ]


@pytest.mark.parametrize("method", OPTIMIZERS)
def test_optimization_methods_sum_to_one(method: str) -> None:
    service = import_module("4_business.portfolio_optimization.service")
    result = service.optimize(_returns(), method)
    weights = result["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert result["is_trade_instruction"] is False
    assert result["status"] == "PROPOSAL"
    assert set(result["risk_contribution"]) == set(weights)
    assert abs(sum(result["risk_contribution"].values()) - 1.0) < 1e-6


def test_constraints_cap_name_weight() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    result = service.optimize(
        _returns(["AAA", "BBB"]),
        "construction",
        constraints={"max_name_weight": 0.55, "max_weight": 0.55},
    )
    assert max(result["weights"].values()) <= 0.55 + 1e-9
    check = service.check_constraints(result["weights"], constraints={"max_name_weight": 0.55, "max_weight": 0.55})
    assert check["passed"] is True
    assert check["is_trade_instruction"] is False


def test_risk_budget_tracks_contribution() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    returns = _returns(["AAA", "BBB", "CCC"])
    budgets = {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}
    result = service.optimize(returns, "risk_budget", risk_budgets=budgets)
    contrib = result["risk_contribution"]
    for asset, budget in budgets.items():
        assert abs(contrib[asset] - budget) < 0.12
    check = service.check_constraints(
        result["weights"],
        returns=returns,
        risk_budgets=budgets,
    )
    names = {item["name"]: item for item in check["checks"]}
    assert names["risk_budget"]["passed"] is True


def test_risk_contribution_sums_to_one() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    returns = _returns()
    weights = service.optimize(returns, "risk_parity")["weights"]
    contrib = service.risk_contribution(weights, returns)
    assert abs(sum(contrib.values()) - 1.0) < 1e-8
    assert min(contrib.values()) >= -1e-9


def test_simulation_clone_modify_optimize_stress_compare() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    store_cls = import_module("4_business.portfolio_optimization.simulation").SimulationStore
    store = store_cls()
    live = sample_snapshot()
    live_weights = service.current_weights(live)
    cloned = service.clone_live(live, label="wave5", store=store)
    assert cloned["is_live"] is False
    assert cloned["live_fund_id"] == live.fund_id
    assert live_weights == service.current_weights(live)

    shifted = dict(cloned["weights"])
    codes = list(shifted)
    shifted[codes[0]] = min(shifted[codes[0]] + 0.05, 0.9)
    shifted[codes[1]] = max(shifted[codes[1]] - 0.05, 0.0)
    total = sum(shifted.values())
    shifted = {k: v / total for k, v in shifted.items()}
    service.modify_simulation(cloned["sim_id"], shifted, store=store)
    assert abs(service.current_weights(live)[codes[0]] - live_weights[codes[0]]) < 1e-12

    review = service.optimize_simulation(cloned["sim_id"], "hrp", store=store)
    assert review["review"]["is_trade_instruction"] is False
    assert review["review"]["trade_instruction"] is None
    assert review["review"]["gate"][-1] == "limits"
    assert all(review["review"]["gate_status"].values())

    stressed = service.stress_simulation(cloned["sim_id"], store=store)
    assert stressed["stress"]["analytic"] == "STRESS"

    compared = service.compare_simulation(cloned["sim_id"], store=store)
    assert compared["live_fund_id"] == live.fund_id
    assert "weight_diff" in compared
    assert "kpi_compare" in compared
    assert compared["is_trade_instruction"] is False


def test_validation_rejects_trade_instruction_status() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    validation = import_module("4_business.portfolio_optimization.validation")
    report = validation.run(sample_snapshot(), "risk_parity")
    assert report["status"] == "PROPOSAL"
    assert report["is_trade_instruction"] is False
    assert report["validation"]["status"] == "PASS"
    assert report["requires_authorization"] is True
    catalog = service.catalog()
    assert report["gate"] == catalog["gate"]


def test_persistence_roundtrip(tmp_path: Path) -> None:
    store_cls = import_module("4_business.portfolio_optimization.simulation").SimulationStore
    path = tmp_path / "sims.json"
    store = store_cls(path)
    cloned = store.clone_live(sample_snapshot(), label="persist")
    store.persist()
    reloaded = store_cls(path)
    loaded = reloaded.get(cloned["sim_id"])
    assert loaded["sim_id"] == cloned["sim_id"]
    assert loaded["label"] == "persist"
    assert abs(sum(loaded["weights"].values()) - 1.0) < 1e-6


def test_unauthorized_live_write_is_blocked() -> None:
    service = import_module("4_business.portfolio_optimization.service")
    locked = import_module("4_business.portfolio_optimization.simulation").LivePortfolioLocked
    store_cls = import_module("4_business.portfolio_optimization.simulation").SimulationStore
    store = store_cls()
    cloned = service.clone_live(sample_snapshot(), store=store)
    with pytest.raises(locked):
        service.modify_simulation(cloned["sim_id"], cloned["weights"], target="live", store=store)
    with pytest.raises(locked):
        service.apply_to_live(cloned["sim_id"], authorized=False, store=store)
    authorized = service.apply_to_live(cloned["sim_id"], authorized=True, store=store)
    assert authorized["live_modified"] is False
    assert authorized["is_trade_instruction"] is False


def test_domain_modules_are_importable() -> None:
    domains = import_module("4_business.portfolio_optimization.domains")
    for name in domains.MODULES:
        mod = import_module(f"4_business.portfolio_optimization.{name}")
        assert mod is not None
    hrp = import_module("4_business.portfolio_optimization.hrp")
    result = hrp.run(_returns())
    assert abs(sum(result["weights"].values()) - 1.0) < 1e-6


def test_business_and_router_do_not_import_riskfolio() -> None:
    router = (ROOT / "2_processing" / "api" / "routers" / "portfolio_opt.py").read_text(encoding="utf-8")
    service = (ROOT / "4_business" / "portfolio_optimization" / "service.py").read_text(encoding="utf-8")
    assert "import riskfolio" not in router
    assert "import riskfolio" not in service
    assert "from riskfolio" not in router
    assert "from riskfolio" not in service


def test_existing_analyze_route_and_optimizer_still_work() -> None:
    router = import_module("2_processing.api.routers.portfolio_opt")
    paths = {route.path for route in router.router.routes}
    assert "/analyze" in paths
    assert "/evaluate" in paths
    assert "/catalog" in paths
    assert "/governed-optimize" in paths
    assert "/simulate/clone" in paths
    optimizer = import_module("2_processing.tools.performance.portfolio_optimizer")
    current = import_module("4_business.portfolio_optimization").current_optimizer
    assert current() is optimizer


def test_adapter_optimize_initializes_without_vendor() -> None:
    adapter = import_module("3_riskengine.adapters.riskfolio").RiskfolioAdapter()
    probe = adapter.initialize()
    result = adapter.optimize(_returns(), "hrp")
    assert probe.name == "riskfolio"
    assert result["engine"] in {"riskfolio", "riskengine_fallback"}
    assert result["is_trade_instruction"] is False
