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

    def lqap(
        self,
        positions: list[dict[str, Any]],
        *,
        scenario_code: str = "SEVERE",
        redemption_pct: float = 100.0,
        cost_multiple: float = 0.5,
        include_current_day: bool = True,
    ) -> dict[str, Any]:
        """彭博 LQAP：期限分布、赎回成本、LQA 字段覆盖。positions 来自 mktdata_lqa 连接后的持仓。"""
        from .lqap import analyze

        return stamp(
            self._bound,
            "LQAP",
            analyze(
                positions,
                scenario_code=scenario_code,
                redemption_pct=redemption_pct,
                cost_multiple=cost_multiple,
                include_current_day=include_current_day,
            ),
            model="bloomberg_lqap",
        )

    def product_stress(
        self,
        *,
        meta: Any | None = None,
        scenario_code: str = "SEVERE",
        redemption_pct: float = 100.0,
        cost_multiple: float = 0.5,
        include_current_day: bool = True,
    ) -> dict[str, Any]:
        """``/investment-risk/indicators`` 产品压力测试：假设 / Overview / 赎回 / Horizon / Stress / LQA 字段。"""

        from .product_stress.pack import fundamentals

        return fundamentals(
            self._bound,
            meta=meta,
            scenario_code=scenario_code,
            redemption_pct=redemption_pct,
            cost_multiple=cost_multiple,
            include_current_day=include_current_day,
        )

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
