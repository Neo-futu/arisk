"""Escalation."""
from __future__ import annotations

from typing import Any

from ..service import default_cases


def run(case_id: str, note: str, *, authorized: bool, **kwargs: Any) -> dict[str, Any]:
    return default_cases().escalate(case_id, note, authorized=authorized, **kwargs)
