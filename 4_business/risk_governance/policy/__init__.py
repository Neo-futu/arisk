"""Risk Policy."""
from __future__ import annotations

from typing import Any

from ..service import risk_policy


def run() -> dict[str, Any]:
    return risk_policy()
