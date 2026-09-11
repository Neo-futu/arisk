"""Investment Risk domain: risk_budget."""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    return analyze_domain("risk_budget", snapshot, **kwargs)
