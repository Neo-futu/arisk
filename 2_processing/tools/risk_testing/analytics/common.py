"""Shared report metadata for independently callable risk analytics."""
from __future__ import annotations

from typing import Any

from ..financepy_adapter import financepy_usage


def implemented_by(
    report: dict[str, Any],
    module: str,
    financepy_calls: list[str] | None,
    supplementary_engine: str,
) -> dict[str, Any]:
    """Attach auditable Python and FinancePy invocation details to a report."""

    report["implementation"] = financepy_usage(
        business_module=module,
        direct_calls=financepy_calls,
        supplementary_engine=supplementary_engine,
    )
    return report
