"""Risk Governance domain catalog."""
from __future__ import annotations

MODULES = (
    "policy",
    "appetite",
    "limits",
    "breach",
    "exception",
    "escalation",
    "action",
    "approval",
    "closure",
    "model_validation",
    "valuation_control",
    "audit",
)

PRE_TRADE_GATE = (
    "order",
    "current_portfolio",
    "proposed_trade",
    "valuation",
    "risk",
    "stress",
    "liquidity",
    "concentration",
    "counterparty",
    "limit",
)

DECISIONS = ("APPROVE", "WARNING", "REJECT")
