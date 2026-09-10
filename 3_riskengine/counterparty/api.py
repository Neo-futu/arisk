"""Counterparty exposure and ORE-style XVA on platform holdings."""
from __future__ import annotations

from typing import Any

from ..risk.kpis import kpi_counterparty_exposure, kpi_epe, kpi_pfe
from ..risk.testing import stamp


class CounterpartyAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def exposure(self) -> dict[str, Any]:
        return kpi_counterparty_exposure(self._bound.snapshot)

    def pfe(self) -> dict[str, Any]:
        return kpi_pfe(self._bound.snapshot)

    def epe(self) -> dict[str, Any]:
        return kpi_epe(self._bound.snapshot)

    def xva(
        self,
        counterparty_hazard: float = 0.02,
        own_hazard: float = 0.01,
        recovery_rate: float = 0.40,
        funding_spread: float = 0.01,
        initial_margin_pct: float = 0.05,
        mva_funding_spread: float = 0.008,
    ) -> dict[str, Any]:
        from ..risk.testing import xva as run

        return run(
            self._bound,
            counterparty_hazard=counterparty_hazard,
            own_hazard=own_hazard,
            recovery_rate=recovery_rate,
            funding_spread=funding_spread,
            initial_margin_pct=initial_margin_pct,
            mva_funding_spread=mva_funding_spread,
        )

    def report(self, **kwargs: Any) -> dict[str, Any]:
        from .aggregate import report as run

        xva = self.xva(**kwargs)
        book = run(self._bound, xva)
        return stamp(
            self._bound,
            "COUNTERPARTY",
            {
                **book,
                "kpi": self.exposure(),
                "pfe": self.pfe()["result"],
                "epe": self.epe()["result"],
            },
            model="ore_trade_xva_allocation",
        )

    def ore_mapping(self) -> dict[str, Any]:
        return self._bound.engine.ore.map_snapshot(self._bound.snapshot)


def exposure(snapshot: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).counterparty().exposure()
