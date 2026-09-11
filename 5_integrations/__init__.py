"""5_integrations — external systems enter ARISK only through adapters."""
from __future__ import annotations

SYSTEMS = (
    "market_data",
    "pms",
    "oms",
    "ems",
    "broker",
    "custodian",
    "fund_admin",
    "accounting",
    "quant",
)

__all__ = ["SYSTEMS"]
