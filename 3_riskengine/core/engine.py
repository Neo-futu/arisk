"""RiskEngine facade: unified valuation and risk over vendor adapters."""
from __future__ import annotations

from typing import Any

from ..adapters.financepy import FinancePyAdapter
from ..adapters.ore import OREAdapter
from ..adapters.riskfolio import RiskfolioAdapter
from .contracts import AnalyticKind, Product, ProductKind, ValuationContext
from .kernel import RevaluationKernel
from .lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .resolve import EngineRef, resolve as resolve_engine


class RiskEngine:
    """ARISK quantitative engine. Business code depends on this type, not vendors."""

    def __init__(self) -> None:
        self.financepy = FinancePyAdapter()
        self.riskfolio = RiskfolioAdapter()
        self.ore = OREAdapter()
        self.financepy.initialize()
        self.riskfolio.initialize()
        self.ore.initialize()

    @property
    def version(self) -> str:
        return RISKENGINE_VERSION

    def adapters_status(self) -> dict[str, Any]:
        return {
            "engine": RISKENGINE_NAME,
            "engine_version": self.version,
            "financepy": self.financepy.describe(),
            "riskfolio": self.riskfolio.describe(),
            "ore": self.ore.describe(),
        }

    def resolve(
        self,
        product: Product | ProductKind | str,
        risk_type: AnalyticKind | str,
        valuation_context: ValuationContext | None = None,
    ) -> EngineRef:
        """Select adapter/model. Business code must not import vendors."""

        return resolve_engine(product, risk_type, valuation_context)

    def bind(self, snapshot: Any) -> "BoundRiskEngine":
        return BoundRiskEngine(self, snapshot)


class BoundRiskEngine:
    """RiskEngine bound to one ARISK portfolio snapshot (fsi.balance_*)."""

    def __init__(self, engine: RiskEngine, snapshot: Any):
        self.engine = engine
        self.snapshot = snapshot
        self._kernel: RevaluationKernel | None = None

    def kernel(self) -> RevaluationKernel:
        if self._kernel is None:
            self._kernel = RevaluationKernel(self.snapshot, self.engine)
        return self._kernel

    def _professional(self) -> RevaluationKernel:
        return self.kernel()

    def valuation(self) -> Any:
        from ..valuation.api import ValuationAPI

        return ValuationAPI(self)

    def risk(self) -> Any:
        from ..risk.api import RiskAPI

        return RiskAPI(self)

    def validation(self) -> Any:
        from ..validation.api import ValidationAPI

        return ValidationAPI(self)

    def limits(self) -> Any:
        from ..limits.api import LimitsAPI

        return LimitsAPI(self)

    def liquidity(self) -> Any:
        from ..liquidity.api import LiquidityAPI

        return LiquidityAPI(self)

    def counterparty(self) -> Any:
        from ..counterparty.api import CounterpartyAPI

        return CounterpartyAPI(self)

    def pnl(self) -> Any:
        from ..pnl.api import PnLAPI

        return PnLAPI(self)

    def stress(self) -> Any:
        from ..stress.api import StressAPI

        return StressAPI(self)

    def scenario(self) -> Any:
        from ..scenario.api import ScenarioAPI

        return ScenarioAPI(self)

    def portfolio(self) -> Any:
        from ..portfolio.api import PortfolioAPI

        return PortfolioAPI(self)

    def governance(self) -> Any:
        from ..governance.api import GovernanceAPI

        return GovernanceAPI(self)

    def market(self) -> Any:
        from ..market.build import market_from_snapshot

        return market_from_snapshot(self.snapshot, self.engine)

    def products(self, view: str = "PRODUCT") -> list[Any]:
        from ..products.assemble import products_from_snapshot

        return products_from_snapshot(self.snapshot, view=view)

    def trades(self, view: str = "LOOK_THROUGH") -> list[Any]:
        from ..trade.build import trades_from_snapshot

        return trades_from_snapshot(self.snapshot, view=view)
