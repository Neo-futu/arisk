"""Broker adapter — simulated fills. Never a live wire in Wave 7."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class BrokerAdapter(ExternalAdapter):
    system = "broker"
    required_permission = "trade.manage"
    record_type = "Fill"

    def _push_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": payload.get("order_id"),
            "security_code": payload.get("security_code"),
            "filled_amount": float(payload.get("amount") or 0.0),
            "status": "FILLED_SIM",
            "venue": "SIM",
            "is_trade_instruction": False,
        }

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._push_impl(payload)
