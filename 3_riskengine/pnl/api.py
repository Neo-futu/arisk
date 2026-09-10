"""PnL explain on successive platform snapshots."""
from __future__ import annotations

from typing import Any, Iterable


class PnLAPI:
    def __init__(self, bound: Any):
        self._bound = bound

    def explain(self, previous: Any) -> dict[str, Any]:
        from ..risk.testing import pnl_explain as run

        return run(self._bound, previous)

    def revalue(self, shocks: Iterable[Any] = ()) -> dict[str, Any]:
        from ..risk.testing import revalue_pack

        return revalue_pack(self._bound, shocks)


def explain(snapshot: Any, previous: Any) -> dict[str, Any]:
    from ..core.engine import RiskEngine

    return RiskEngine().bind(snapshot).pnl().explain(previous)
