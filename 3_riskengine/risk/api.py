"""Unified risk interface: calculate / exposure / sensitivity / stress / scenario."""
from __future__ import annotations

from typing import Any, Iterable

from ..core.lineage import RISKENGINE_VERSION


class RiskAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def _stamp(self, report: dict[str, Any], model: str) -> dict[str, Any]:
        snapshot = self._bound.snapshot
        report.setdefault("engine_version", RISKENGINE_VERSION)
        report.setdefault("model", model)
        report.setdefault("model_version", RISKENGINE_VERSION)
        report.setdefault("valuation_date", snapshot.as_of_date.isoformat())
        report.setdefault("market_data_date", snapshot.as_of_date.isoformat())
        report.setdefault("curve", "FinancePy FlatDiscountCurve (DiscountCurveFlat compatible)")
        adapters = self._bound.engine.adapters_status()
        report.setdefault("adapters", adapters)
        return report

    def calculate(self, analytic: str, **kwargs: Any) -> dict[str, Any]:
        method = analytic.lower()
        if not hasattr(self, method) or method == "calculate":
            raise ValueError(f"Unsupported risk analytic: {analytic}")
        return getattr(self, method)(**kwargs)

    def exposure(self, shocks: Iterable[Any] = ()) -> dict[str, Any]:
        book = self._bound.portfolio().aggregate(shocks=tuple(shocks))
        return self._stamp(
            {
                "analytic": "EXPOSURE",
                "base_pv": book["base_pv"],
                "shocked_pv": book["shocked_pv"],
                "pnl": book["pnl"],
                "gross": book["gross"],
                "net": book["net"],
                "leverage": book["leverage"],
                "by_asset_class": book["by_asset_class"],
                "trade_values": book["positions"],
                "view": book["view"],
            },
            "portfolio_aggregation",
        )

    def sensitivity(self, shocks: Iterable[Any]) -> dict[str, Any]:
        from .testing import sensitivity as run

        return run(self._bound, shocks)

    def stress(self, scenario: Any) -> dict[str, Any]:
        from .testing import stress as run

        return run(self._bound, scenario)

    def scenario(self, scenario: Any) -> dict[str, Any]:
        from .testing import scenario as run

        return run(self._bound, scenario)

    def reverse_stress(
        self,
        scenario: Any,
        target_loss_pct_nav: float,
        max_scale: float = 20.0,
    ) -> dict[str, Any]:
        from .testing import reverse_stress as run

        return run(self._bound, scenario, target_loss_pct_nav, max_scale)

    def tail_risk(self, sigma_levels: Iterable[Any], capital_buffer: float) -> dict[str, Any]:
        from .testing import tail_risk as run

        return run(self._bound, sigma_levels, capital_buffer)

    def krd(self, bump_bps: float = 1.0) -> dict[str, Any]:
        from .testing import krd as run

        return run(self._bound, bump_bps)

    def pnl_explain(self, previous: Any) -> dict[str, Any]:
        from .testing import pnl_explain as run

        return run(self._bound, previous)

    def historical_backtest(
        self,
        market: Any | None = None,
        weight_mode: str = "CURRENT",
        custom_weights: Any | None = None,
    ) -> dict[str, Any]:
        from .testing import historical_backtest as run

        return run(self._bound, market=market, weight_mode=weight_mode, custom_weights=custom_weights)

    def var_backtest(self, confidence: float = 0.99, window: int = 60) -> dict[str, Any]:
        from .testing import var_backtest as run

        return run(self._bound, confidence=confidence, window=window)

    def xva(self, **kwargs: Any) -> dict[str, Any]:
        from .testing import xva as run

        return run(self._bound, **kwargs)

    def kpis(self, confidence: float = 0.99, benchmark_returns: Any = None) -> dict[str, Any]:
        from .kpis import compute_kpi_pack

        return compute_kpi_pack(
            self._bound.snapshot,
            confidence=confidence,
            benchmark_returns=benchmark_returns,
        )

    def var(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        return self._bound.portfolio().var(confidence=confidence, scope=scope)

    def cvar(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        return self._bound.portfolio().cvar(confidence=confidence, scope=scope)

    def contribution(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        return self._bound.portfolio().contribution(confidence=confidence, returns=returns)

    def optimize(self, method: str, **kwargs: Any) -> dict[str, Any]:
        return self._bound.portfolio().optimize(method, **kwargs)

    def portfolio(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        return self._bound.portfolio().risk(confidence=confidence, returns=returns)

    def fund(self, *, confidence: float = 0.99) -> dict[str, Any]:
        return self._bound.portfolio().fund_risk(confidence=confidence)

    def liquidity(self) -> dict[str, Any]:
        return self._bound.liquidity().report()

    def counterparty(self) -> dict[str, Any]:
        return self._bound.counterparty().report()

    def mmf(self) -> dict[str, Any]:
        return self._bound.liquidity().mmf()


def calculate(snapshot: Any, analytic: str, **kwargs: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).risk().calculate(analytic, **kwargs)


def exposure(snapshot: Any, shocks: Iterable[Any] = ()) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).risk().exposure(shocks)


def sensitivity(snapshot: Any, shocks: Iterable[Any]) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).risk().sensitivity(shocks)


def stress(snapshot: Any, scenario: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).risk().stress(scenario)


def scenario(snapshot: Any, scenario_def: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).risk().scenario(scenario_def)
