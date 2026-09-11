"""Equal risk contribution / risk parity."""
from __future__ import annotations

from typing import Any, Mapping

from ..service import optimize


def run(returns: Any, *, constraints: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return optimize(returns, "risk_parity", constraints=constraints, **kwargs)
