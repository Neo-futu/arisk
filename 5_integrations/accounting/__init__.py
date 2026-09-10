"""Fund accounting adapter — books and records, not a second NAV master."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class AccountingAdapter(ExternalAdapter):
    system = "accounting"
    required_permission = "portfolio.oversight"
    record_type = "AccountingEntry"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "fund_id": payload.get("fund_id") or "TEST001",
            "pnl": float(payload.get("pnl") or 0.0),
            "entries": payload.get("entries") or [],
        }
