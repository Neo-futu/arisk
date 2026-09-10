"""Black-Litterman posterior then min-risk."""
from __future__ import annotations

from typing import Any, Mapping

from ..service import optimize


def run(returns: Any, *, constraints: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return optimize(returns, "black_litterman", constraints=constraints, **kwargs)
