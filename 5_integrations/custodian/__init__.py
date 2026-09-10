"""Custodian adapter — custody positions and cash breaks."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class CustodianAdapter(ExternalAdapter):
    system = "custodian"
    required_permission = "portfolio.view"
    record_type = "CustodyPosition"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "fund_id": payload.get("fund_id") or "TEST001",
            "cash": float(payload.get("cash") or 100_000.0),
            "positions": payload.get("positions") or [],
            "breaks": [],
        }
