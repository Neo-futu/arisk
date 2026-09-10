"""OMS adapter — order capture. Does not send broker instructions by itself."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class OMSAdapter(ExternalAdapter):
    system = "oms"
    required_permission = "trade.manage"
    record_type = "Order"

    def _push_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": str(payload.get("order_id") or "ord-sim"),
            "security_code": payload.get("security_code"),
            "side": str(payload.get("side") or "BUY").upper(),
            "amount": float(payload.get("amount") or 0.0),
            "status": "NEW",
            "is_trade_instruction": False,
        }

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._push_impl(payload)
