"""Model validation control."""
from __future__ import annotations

from typing import Any

from ..service import model_validation


def run(snapshot: Any) -> dict[str, Any]:
    return model_validation(snapshot)
