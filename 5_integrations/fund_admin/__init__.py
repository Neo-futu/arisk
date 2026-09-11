"""Fund administrator adapter — official NAV packs."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class FundAdminAdapter(ExternalAdapter):
    system = "fund_admin"
    required_permission = "portfolio.oversight"
    record_type = "OfficialNAV"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "fund_id": payload.get("fund_id") or "TEST001",
            "nav": float(payload.get("nav") or 1_000_000.0),
            "share_class": payload.get("share_class") or "A",
            "status": "OFFICIAL",
        }
