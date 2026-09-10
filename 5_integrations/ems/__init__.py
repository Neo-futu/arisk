"""EMS adapter — execution routing status."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class EMSAdapter(ExternalAdapter):
    system = "ems"
    required_permission = "trade.manage"
    record_type = "Execution"

    def _push_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": payload.get("order_id"),
            "route": payload.get("route") or "SIM",
            "status": "ROUTED",
            "filled_amount": float(payload.get("amount") or 0.0),
        }

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._push_impl(payload)
