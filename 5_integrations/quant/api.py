"""Quant API — Python / Jupyter surface over RiskEngine and business use cases.

Business still must not call external vendors; this module only calls
3_riskengine / 4_business. External I/O goes through 5_integrations adapters.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

_engine = import_module("3_riskengine")
_kpis = import_module("3_riskengine.risk.kpis")
_valuation = import_module("3_riskengine.valuation")
_opt = import_module("4_business.portfolio_optimization.service")
_rt = import_module("4_business.risk_testing.service")
_models = import_module("2_processing.tools.risk_testing.models")
SCENARIOS = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS

Shock = _models.Shock
RiskFactorType = _models.RiskFactorType
ShockMode = _models.ShockMode
RiskEngine = _engine.RiskEngine

QUANT_CONTRACT = {
    "risk": ("portfolio", "exposure", "var", "cvar", "stress", "liquidity", "counterparty"),
    "portfolio": ("optimize", "simulate"),
    "valuation": ("price",),
    "testing": ("run",),
    "channels": ("Python", "Jupyter", "CLI", "REST"),
}


def catalog() -> dict[str, Any]:
    return {
        "module": "quant",
        "contract": QUANT_CONTRACT,
        "engine": RiskEngine().adapters_status()["engine"],
        "channels": list(QUANT_CONTRACT["channels"]),
        "rest": "/quant",
    }


class _RiskNS:
    def portfolio(self, snapshot: Any) -> dict[str, Any]:
        pack = _kpis.compute_kpi_pack(snapshot)
        return {
            "fund_id": snapshot.fund_id,
            "as_of_date": snapshot.as_of_date.isoformat(),
            "net_asset": snapshot.net_asset,
            "positions": [
                {"security_code": p.security_code, "market_value_base": p.market_value_base}
                for p in snapshot.positions
            ],
            "kpis": pack["kpis"],
            "engine": pack["engine"],
        }

    def exposure(self, snapshot: Any) -> dict[str, Any]:
        return _engine.risk.exposure(snapshot)

    def var(self, snapshot: Any, confidence: float = 0.99) -> dict[str, Any]:
        return _kpis.kpi_var(snapshot, confidence=confidence)

    def cvar(self, snapshot: Any, confidence: float = 0.99) -> dict[str, Any]:
        return _kpis.kpi_cvar(snapshot, confidence=confidence)

    def stress(self, snapshot: Any, scenario_id: str = "gfc_2008") -> dict[str, Any]:
        scenario = SCENARIOS.get(scenario_id) or next(iter(SCENARIOS.values()))
        return _engine.risk.stress(snapshot, scenario)

    def liquidity(self, snapshot: Any) -> dict[str, Any]:
        return _kpis.kpi_liquidity(snapshot)

    def counterparty(self, snapshot: Any) -> dict[str, Any]:
        return _kpis.kpi_counterparty_exposure(snapshot)


class _PortfolioNS:
    def optimize(self, snapshot: Any, method: str = "hrp", **kwargs: Any) -> dict[str, Any]:
        return _opt.optimize_and_govern(snapshot, method, **kwargs)

    def simulate(self, snapshot: Any, *, label: str = "quant") -> dict[str, Any]:
        return _opt.clone_live(snapshot, label=label)


class _ValuationNS:
    def price(self, snapshot: Any) -> dict[str, Any]:
        priced = _valuation.price(snapshot)
        return {
            "base_pv": priced.base_pv,
            "engine": priced.context.get("engine"),
            "engine_version": priced.context.get("engine_version"),
            "data_quality": priced.context.get("data_quality"),
        }


class _TestingNS:
    def run(self, snapshot: Any, analytic: str = "SENSITIVITY") -> dict[str, Any]:
        return _rt.run(snapshot, analytic)


risk = _RiskNS()
portfolio = _PortfolioNS()
valuation = _ValuationNS()
testing = _TestingNS()


class QuantAPI:
    """Object-style session used by Jupyter / REST / CLI."""

    def __init__(self, snapshot: Any):
        self.snapshot = snapshot
        self.risk = risk
        self.portfolio = portfolio
        self.valuation = valuation
        self.testing = testing

    def call(self, namespace: str, method: str, **kwargs: Any) -> dict[str, Any]:
        target = getattr(self, namespace)
        func = getattr(target, method)
        return func(self.snapshot, **kwargs)
