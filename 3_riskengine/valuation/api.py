"""Unified valuation interface: price / revalue / greeks / cashflows / pnl."""
from __future__ import annotations

from typing import Any, Iterable

from ..core.contracts import ValuationResult, ViewMode, lineage_context
from ..core.lineage import DEFAULT_ASSUMPTIONS, RISKENGINE_NAME, RISKENGINE_VERSION
from . import pipeline


class ValuationAPI:
    """Product + Market + Model valuation. FinancePy / ORE stay in adapters."""

    def __init__(self, bound: Any):
        self._bound = bound

    def _context(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot = self._bound.snapshot
        ctx = lineage_context(
            valuation_date=snapshot.as_of_date,
            market_data_date=snapshot.as_of_date,
            curve="FinancePy FlatDiscountCurve (DiscountCurveFlat compatible)",
            model="product_market_model",
            engine_version=RISKENGINE_VERSION,
            engine=RISKENGINE_NAME,
            assumptions=DEFAULT_ASSUMPTIONS,
            data_quality=getattr(snapshot, "data_quality", {}),
            portfolio_id=str(getattr(snapshot, "fund_id", "") or ""),
        )
        if extra:
            ctx["parameters"] = extra
        return ctx

    def _wrap(self, raw: dict[str, Any], extra: dict[str, Any] | None = None) -> ValuationResult:
        context = self._context(extra)
        raw.setdefault("engine_version", RISKENGINE_VERSION)
        raw.setdefault("model", context["model"])
        raw.setdefault("model_version", RISKENGINE_VERSION)
        raw.setdefault("curve", context["curve"])
        raw.setdefault("valuation_date", context["valuation_date"])
        raw.setdefault("market_data_date", context["market_data_date"])
        raw.setdefault("data_quality", getattr(self._bound.snapshot, "data_quality", {}))
        return ValuationResult(
            base_pv=float(raw.get("base_pv", 0.0)),
            shocked_pv=float(raw.get("shocked_pv", raw.get("base_pv", 0.0))),
            pnl=float(raw.get("pnl", 0.0)),
            pnl_pct_nav=raw.get("pnl_pct_nav"),
            trade_values=list(raw.get("trade_values") or []),
            context=context,
            raw=raw,
        )

    def price(self, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> ValuationResult:
        return self._wrap(pipeline.revalue(self._bound, shocks=(), view=view))

    def revalue(
        self,
        shocks: Iterable[Any] = (),
        view: ViewMode | str = ViewMode.LOOK_THROUGH,
    ) -> ValuationResult:
        return self._wrap(
            pipeline.revalue(self._bound, shocks=tuple(shocks), view=view),
            extra={"shocks": True, "view": str(getattr(view, "value", view))},
        )

    def greeks(
        self,
        shocks: Iterable[Any],
        view: ViewMode | str = ViewMode.LOOK_THROUGH,
    ) -> dict[str, Any]:
        report = pipeline.greeks(self._bound, shocks, view=view)
        context = self._context({"view": str(getattr(view, "value", view))})
        report.setdefault("engine_version", RISKENGINE_VERSION)
        report.setdefault("engine", RISKENGINE_NAME)
        report.setdefault("valuation_date", context["valuation_date"])
        report.setdefault("market_data_date", context["market_data_date"])
        report.setdefault("curve", context["curve"])
        report.setdefault("model", "central_difference_greeks")
        return report

    def cashflows(self, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> dict[str, Any]:
        report = pipeline.cashflows(self._bound, view=view)
        context = self._context({"view": str(getattr(view, "value", view))})
        report.setdefault("engine_version", RISKENGINE_VERSION)
        report.setdefault("engine", RISKENGINE_NAME)
        report.setdefault("valuation_date", context["valuation_date"])
        report.setdefault("market_data_date", context["market_data_date"])
        report.setdefault("curve", context["curve"])
        report.setdefault("model", context["model"])
        report.setdefault("data_quality", getattr(self._bound.snapshot, "data_quality", {}))
        return report

    def pnl(
        self,
        shocks: Iterable[Any] = (),
        previous: Any | None = None,
        view: ViewMode | str = ViewMode.LOOK_THROUGH,
    ) -> dict[str, Any]:
        if previous is not None:
            from ..risk.testing import pnl_explain

            report = pnl_explain(self._bound, previous)
            report.setdefault("engine_version", RISKENGINE_VERSION)
            return report
        return self.revalue(shocks, view=view).raw


def price(snapshot: Any, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> ValuationResult:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).valuation().price(view=view)


def revalue(
    snapshot: Any,
    shocks: Iterable[Any] = (),
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> ValuationResult:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).valuation().revalue(shocks, view=view)


def greeks(
    snapshot: Any,
    shocks: Iterable[Any],
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).valuation().greeks(shocks, view=view)


def cashflows(snapshot: Any, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).valuation().cashflows(view=view)


def pnl(
    snapshot: Any,
    shocks: Iterable[Any] = (),
    previous: Any | None = None,
    view: ViewMode | str = ViewMode.LOOK_THROUGH,
) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).valuation().pnl(shocks, previous=previous, view=view)
