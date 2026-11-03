"""PnL explain + 业绩归因（Brinson / Campisi / 贡献）。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


class PnLAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def explain(self, previous: Any) -> dict[str, Any]:
        from ..risk.testing import pnl_explain as run

        return run(self._bound, previous)

    def revalue(self, shocks: Iterable[Any] = ()) -> dict[str, Any]:
        from ..risk.testing import revalue_pack

        return revalue_pack(self._bound, shocks)

    def attribution(
        self,
        *,
        meta: Mapping[str, Any] | None = None,
        brinson_method: str = "BHB",
        brinson_multi: bool = True,
        brinson_group: str = "asset",
        campisi_benchmark: bool = True,
        campisi_multi: bool = True,
        campisi_group: str = "industry",
        contrib_mode: str = "daily",
        contrib_link: str = "carino",
        contrib_group: str = "symbol",
        top_n: int = 10,
    ) -> dict[str, Any]:
        """``/investment-risk/indicators`` 业绩归因 Tab：摘要 / 贡献 / Brinson / Campisi / Beta。"""

        from .attribution.pack import fundamentals

        return fundamentals(
            self._bound,
            meta=meta,
            brinson_method=brinson_method,
            brinson_multi=brinson_multi,
            brinson_group=brinson_group,
            campisi_benchmark=campisi_benchmark,
            campisi_multi=campisi_multi,
            campisi_group=campisi_group,
            contrib_mode=contrib_mode,
            contrib_link=contrib_link,
            contrib_group=contrib_group,
            top_n=top_n,
        )


def explain(snapshot: Any, previous: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).pnl().explain(previous)
