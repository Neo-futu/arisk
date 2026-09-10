"""Breach case opening."""
from __future__ import annotations

from typing import Any, Mapping

from ..service import default_cases


def run(evaluation: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return default_cases().open_from_evaluation(evaluation, **kwargs)
