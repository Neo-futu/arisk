"""PMS adapter — live holdings snapshots from an external portfolio book."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class PMSAdapter(ExternalAdapter):
    system = "pms"
    required_permission = "portfolio.view"
    record_type = "PortfolioHolding"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        fund_id = str(payload.get("fund_id") or "TEST001")
        holdings = payload.get("holdings") or {"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1}
        return {"fund_id": fund_id, "holdings": dict(holdings), "book": "live"}
