"""Portfolio aggregation API: Portfolio Risk, Fund Risk, VaR/CVaR/RC/optimize."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.contracts import ViewMode
from ..core.lineage import RISKENGINE_VERSION
from .aggregate import aggregate
from .measures import fund_risk, optimize_book, portfolio_risk


class PortfolioAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def aggregate(
        self,
        view: ViewMode | str = ViewMode.LOOK_THROUGH,
        shocks: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        report = aggregate(self._bound, view=view, shocks=shocks)
        report.setdefault("engine_version", RISKENGINE_VERSION)
        return report

    def risk(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        """Look-through Portfolio Risk."""

        return portfolio_risk(self._bound, confidence=confidence, returns=returns)

    def fund_risk(self, *, confidence: float = 0.99) -> dict[str, Any]:
        """Share-class Fund Risk (PRODUCT view + NAV history)."""

        return fund_risk(self._bound, confidence=confidence)

    def var(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        pack = self.fund_risk(confidence=confidence) if scope == "fund" else self.risk(confidence=confidence)
        return {
            "analytic": "VAR",
            "scope": pack["scope"],
            **pack["var_cvar"],
            "nav": pack["nav"],
        }

    def cvar(self, *, confidence: float = 0.99, scope: str = "fund") -> dict[str, Any]:
        pack = self.var(confidence=confidence, scope=scope)
        pack["analytic"] = "CVAR"
        return pack

    def contribution(self, *, confidence: float = 0.99, returns: Any | None = None) -> dict[str, Any]:
        pack = self.risk(confidence=confidence, returns=returns)
        return {
            "analytic": "RISK_CONTRIBUTION",
            "scope": "PORTFOLIO",
            **pack["risk_contribution"],
            "weights": {row["security_code"]: row["weight"] for row in pack["positions"]},
            "engine_version": RISKENGINE_VERSION,
        }

    def optimize(
        self,
        method: str,
        *,
        returns: Any | None = None,
        constraints: Mapping[str, Any] | None = None,
        views: Mapping[str, float] | None = None,
        risk_budgets: Mapping[str, float] | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        return optimize_book(
            self._bound,
            method,
            returns=returns,
            constraints=constraints,
            views=views,
            risk_budgets=risk_budgets,
            confidence=confidence,
        )

    def fundamentals(self, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """``/portfolio-cockpit`` 五大业务模块：组合 / 规模 / 持仓资产类型 / 收益 / 净值。"""

        from .cockpit import fundamentals

        return fundamentals(self._bound, meta=meta)

    def overview(
        self,
        *,
        meta: Mapping[str, Any] | None = None,
        history: Any | None = None,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """``/investment-risk/overview``：组合 / 区间收益 / 配置 / Top10 股债 / 行业。"""

        from .overview import fundamentals as overview_fundamentals

        return overview_fundamentals(self._bound, meta=meta, history=history, top_n=top_n)

    def basic_info(
        self,
        *,
        meta: Mapping[str, Any] | None = None,
        managers: Any | None = None,
    ) -> dict[str, Any]:
        """``/investment-risk/indicators`` 基本信息：组合 / 币种 / 成立日 / WAM·WAL / 投管人员。"""

        from .basic_info import fundamentals as basic_info_fundamentals

        return basic_info_fundamentals(self._bound, meta=meta, managers=managers)

    def risk_indicators(
        self,
        *,
        meta: Mapping[str, Any] | None = None,
        confidence: float = 0.99,
        horizon_days: int = 1,
        rolling_window: int = 20,
        period_start: Any | None = None,
        period_end: Any | None = None,
    ) -> dict[str, Any]:
        """``/investment-risk/indicators#risk-exposure`` 风险指标：核心五卡 / 滚动波动 / VaR三方法 / 六大风控类型。"""

        from .risk_indicators import fundamentals as risk_indicators_fundamentals

        return risk_indicators_fundamentals(
            self._bound,
            meta=meta,
            confidence=confidence,
            horizon_days=horizon_days,
            rolling_window=rolling_window,
            period_start=period_start,
            period_end=period_end,
        )

    def cockpit(self, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """``/portfolio-cockpit`` 单组合行 + 业务模块打包。"""

        from .cockpit import row_from_snapshot

        return row_from_snapshot(self._bound, meta=meta)

    def portfolio_opt(
        self,
        *,
        meta: Mapping[str, Any] | None = None,
        run_governed: bool = True,
        governed_method: str = "hrp",
    ) -> dict[str, Any]:
        """``/portfolio-opt``：收益模型 / 有效前沿 / 画像 / HRP 闸门（提案非成交）。"""

        from .optimization.pack import fundamentals

        return fundamentals(
            self._bound,
            meta=meta,
            run_governed=run_governed,
            governed_method=governed_method,
        )
