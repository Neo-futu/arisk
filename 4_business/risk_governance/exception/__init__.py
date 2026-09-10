"""Limit exception requests."""
from __future__ import annotations

from typing import Any

from ..service import default_cases


def run(case_id: str, reason: str, *, authorized: bool, **kwargs: Any) -> dict[str, Any]:
    return default_cases().request_exception(case_id, reason, authorized=authorized, **kwargs)
