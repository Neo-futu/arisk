"""Risk Governance use-case layer over the unified Limit Engine."""
from __future__ import annotations

import uuid
from datetime import date
from importlib import import_module
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from .audit_log import AuditLog, default_audit
from .domains import DECISIONS, MODULES, PRE_TRADE_GATE
from .pre_trade import decision_from_state, run_pre_trade

_engine = import_module("3_riskengine")
_limits = import_module("3_riskengine.limits")
_ir = import_module("4_business.investment_risk.service")
_loader = import_module("2_processing.tools.risk_testing.loader")

RiskEngine = _engine.RiskEngine


class Unauthorized(PermissionError):
    """Raised when a governance mutation is attempted without authorization."""


class HardBreachLocked(PermissionError):
    """HARD_BREACH cannot be excepted or approved through to a live change."""


def catalog() -> dict[str, Any]:
    status = RiskEngine().adapters_status()
    limits = _limits.catalog()
    return {
        "module": "risk_governance",
        "engine": status["engine"],
        "engine_version": status["engine_version"],
        "limit_engine": "3_riskengine.limits",
        "modules": list(MODULES),
        "states": limits["states"],
        "limit_ids": limits["limit_ids"],
        "pre_trade_gate": list(PRE_TRADE_GATE),
        "decisions": list(DECISIONS),
        "consumers": ["investment_risk", "portfolio_optimization", "risk_testing", "pre_trade"],
        "frontend_routes": "/risk-governance",
        "pre_trade_path": "/api/v1/risk/pre-trade",
    }


def risk_policy() -> dict[str, Any]:
    limits = _limits.catalog()
    return {
        "policy_id": "default",
        "name": "ARISK default risk policy",
        "appetite": "Stay inside published limits; HARD_BREACH is non-overridable.",
        "limits": limits["defaults"],
        "states": limits["states"],
        "engine": "3_riskengine.limits",
    }


def risk_appetite() -> dict[str, Any]:
    policy = risk_policy()
    return {
        "statement": policy["appetite"],
        "warning_utilization": 0.8,
        "breach_utilization": 1.0,
        "hard_breach_utilization": 1.1,
        "policy_id": policy["policy_id"],
    }


def evaluate_limits(snapshot: Any, *, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _limits.evaluate(snapshot, policy=policy)


def attach_limits(snapshot: Any, payload: dict[str, Any], *, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload["limits"] = evaluate_limits(snapshot, policy=policy)
    payload["limit_engine"] = "3_riskengine.limits"
    return payload


def model_validation(snapshot: Any) -> dict[str, Any]:
    bound = RiskEngine().bind(snapshot)
    pricing = bound.validation().pricing()
    return {
        "control": "model_validation",
        "status": pricing.status,
        "checks": pricing.checks,
        "engine": pricing.context.get("engine"),
    }


def valuation_control(snapshot: Any) -> dict[str, Any]:
    priced = RiskEngine().bind(snapshot).valuation().price()
    ok = priced.base_pv > 0
    return {
        "control": "valuation_control",
        "status": "PASS" if ok else "FAIL",
        "base_pv": priced.base_pv,
        "engine": priced.context.get("engine"),
    }


class GovernanceCases:
    def __init__(self, audit: AuditLog | None = None) -> None:
        self._cases: dict[str, dict[str, Any]] = {}
        self.audit = audit or default_audit()

    def open_from_evaluation(
        self,
        evaluation: Mapping[str, Any],
        *,
        actor: str = "system",
        fund_id: str | None = None,
    ) -> dict[str, Any]:
        case_id = f"gov-{uuid.uuid4().hex[:12]}"
        record = {
            "case_id": case_id,
            "kind": "breach" if evaluation.get("state") in {"BREACH", "HARD_BREACH", "WARNING"} else "monitor",
            "state": evaluation.get("state"),
            "status": "OPEN",
            "fund_id": fund_id,
            "evaluation": dict(evaluation),
            "exception": None,
            "escalation": None,
            "actions": [],
            "approval": None,
            "closed": False,
        }
        self._cases[case_id] = record
        self.audit.record("BREACH_OPENED" if record["kind"] == "breach" else "MONITOR_OPENED", actor=actor, payload={"case_id": case_id, "state": record["state"]})
        return record

    def get(self, case_id: str) -> dict[str, Any]:
        if case_id not in self._cases:
            raise KeyError(case_id)
        return self._cases[case_id]

    def request_exception(self, case_id: str, reason: str, *, authorized: bool, actor: str = "system") -> dict[str, Any]:
        self._require(authorized)
        record = self.get(case_id)
        if record["state"] == "HARD_BREACH":
            raise HardBreachLocked("HARD_BREACH cannot be excepted")
        record["exception"] = {"reason": reason, "status": "REQUESTED", "actor": actor}
        self.audit.record("EXCEPTION_REQUESTED", actor=actor, payload={"case_id": case_id, "reason": reason})
        return record

    def escalate(self, case_id: str, note: str, *, authorized: bool, actor: str = "system") -> dict[str, Any]:
        self._require(authorized)
        record = self.get(case_id)
        record["escalation"] = {"note": note, "actor": actor, "status": "ESCALATED"}
        self.audit.record("ESCALATED", actor=actor, payload={"case_id": case_id, "note": note})
        return record

    def action(self, case_id: str, note: str, *, authorized: bool, actor: str = "system") -> dict[str, Any]:
        self._require(authorized)
        record = self.get(case_id)
        record["actions"].append({"note": note, "actor": actor})
        self.audit.record("ACTION", actor=actor, payload={"case_id": case_id, "note": note})
        return record

    def approve(self, case_id: str, *, authorized: bool, actor: str = "system") -> dict[str, Any]:
        self._require(authorized)
        record = self.get(case_id)
        if record["state"] == "HARD_BREACH":
            raise HardBreachLocked("HARD_BREACH cannot be approved as a live override")
        if not record.get("exception"):
            raise Unauthorized("exception must be requested before approval")
        record["approval"] = {"actor": actor, "status": "APPROVED"}
        record["exception"]["status"] = "APPROVED"
        self.audit.record("APPROVED", actor=actor, payload={"case_id": case_id})
        return record

    def close(self, case_id: str, *, authorized: bool, actor: str = "system") -> dict[str, Any]:
        self._require(authorized)
        record = self.get(case_id)
        record["closed"] = True
        record["status"] = "CLOSED"
        self.audit.record("CLOSED", actor=actor, payload={"case_id": case_id})
        return record

    def _require(self, authorized: bool) -> None:
        if not authorized:
            raise Unauthorized("governance mutation requires authorization")


_CASES: GovernanceCases | None = None


def default_cases() -> GovernanceCases:
    global _CASES
    if _CASES is None:
        _CASES = GovernanceCases()
    return _CASES


async def load_snapshot(fund_id: str, as_of_date: date, db: AsyncSession, lookback_days: int = 500):
    return await _loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days)


def investment_risk_with_limits(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    pack = _ir.compute_kpi_pack(snapshot, **kwargs)
    return attach_limits(snapshot, pack)
