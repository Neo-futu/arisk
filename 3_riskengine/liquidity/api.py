"""Liquidity analytics: product buckets, MMF redemption, SFC WAM/WAL."""
from __future__ import annotations

from typing import Any

from ..risk.kpis import kpi_liquidity
from ..risk.testing import stamp


class LiquidityAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def ratio(self) -> dict[str, Any]:
        return kpi_liquidity(self._bound.snapshot)

    def buckets(self) -> dict[str, Any]:
        from .buckets import report as run

        return stamp(self._bound, "LIQUIDITY", run(self._bound), model="product_liquidity_buckets")

    def redemption(self, redemption_pct: float = 20.0) -> dict[str, Any]:
        from .redemption import run

        return stamp(
            self._bound,
            "REDEMPTION",
            run(self._bound, redemption_pct),
            model="liquidity_waterfall",
        )

    def mmf(self) -> dict[str, Any]:
        from .mmf import sfc_metrics

        return stamp(self._bound, "MMF_SFC", sfc_metrics(self._bound), model="mmf_look_through_sfc")

    def report(self, redemption_pct: float = 20.0) -> dict[str, Any]:
        ratio = self.ratio()
        buckets = self.buckets()
        mmf = self.mmf()
        cover = self.redemption(redemption_pct)
        t0 = float(buckets["buckets"]["T0"]["base_pv"])
        return stamp(
            self._bound,
            "LIQUIDITY",
            {
                "kpi": ratio,
                "buckets": buckets["buckets"],
                "positions": buckets["positions"],
                "by_asset_class": buckets["by_asset_class"],
                "liquid_pv": buckets["liquid_pv"],
                "liquid_pct_nav": buckets["liquid_pct_nav"],
                "funding": {"cash_t0": t0, "pct_nav": (t0 / self._bound.snapshot.net_asset * 100.0) if self._bound.snapshot.net_asset else None},
                "redemption": cover,
                "mmf": mmf,
                "ore_app": False,
            },
            model="product_liquidity_aggregation",
        )


def ratio(snapshot: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).liquidity().ratio()
