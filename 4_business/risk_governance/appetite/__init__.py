"""Risk Appetite."""
from __future__ import annotations

from typing import Any

from ..service import risk_appetite


def run() -> dict[str, Any]:
    return risk_appetite()
