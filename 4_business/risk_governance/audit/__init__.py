"""Audit trail listing."""
from __future__ import annotations

from typing import Any

from ..service import default_audit


def run(event_type: str | None = None) -> list[dict[str, Any]]:
    return default_audit().entries(event_type)
