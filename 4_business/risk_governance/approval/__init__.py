"""Approval."""
from __future__ import annotations

from typing import Any

from ..service import default_cases


def run(case_id: str, *, authorized: bool, **kwargs: Any) -> dict[str, Any]:
    return default_cases().approve(case_id, authorized=authorized, **kwargs)
