"""Valuation control."""
from __future__ import annotations

from typing import Any

from ..service import valuation_control


def run(snapshot: Any) -> dict[str, Any]:
    return valuation_control(snapshot)
