"""Evaluate a snapshot against the unified limit catalog."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from .metrics import collect_metrics
from .policy import LIMIT_IDS, LimitSpec, policy_from_overrides, spec_as_dict
from .states import LimitState, classify, worst


def _utilization(value: float, spec: LimitSpec) -> float:
    if spec.direction == "MIN":
        if spec.limit <= 0:
            return 0.0
        if value <= 0:
            return spec.hard
        return spec.limit / value
    if spec.limit <= 0:
        return spec.hard if value > 0 else 0.0
    return value / spec.limit


def _member_report(name: str, value: float, spec: LimitSpec) -> dict[str, Any]:
    utilization = _utilization(value, spec)
    state = classify(utilization, warning=spec.warning, hard=spec.hard)
    return {
        "name": name,
        "value": value,
        "limit": spec.limit,
        "utilization": utilization,
        "state": state.value,
        "direction": spec.direction,
    }


def evaluate(
    snapshot: Any,
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    specs = policy_from_overrides(dict(policy) if policy else None)
    metrics = collect_metrics(snapshot)
    rows: dict[str, Any] = {}
    states: list[LimitState] = []
    for limit_id in LIMIT_IDS:
        spec: LimitSpec = specs[limit_id]
        raw = metrics[limit_id]
        if spec.grouped:
            members = [_member_report(name, float(value), spec) for name, value in sorted(raw.items())]
            if not members:
                members = [_member_report("(none)", 0.0, spec)]
            worst_member = max(members, key=lambda item: item["utilization"])
            row = {
                **spec_as_dict(spec),
                "value": worst_member["value"],
                "utilization": worst_member["utilization"],
                "state": worst_member["state"],
                "members": members,
                "worst_member": worst_member["name"],
            }
        else:
            member = _member_report(limit_id, float(raw), spec)
            row = {**spec_as_dict(spec), **member}
            row.pop("name", None)
        rows[limit_id] = row
        states.append(LimitState(row["state"]))

    aggregate = worst(*states)
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "state": aggregate.value,
        "passed": aggregate in {LimitState.GREEN, LimitState.WARNING},
        "limits": rows,
        "limit_ids": list(LIMIT_IDS),
        "is_trade_instruction": False,
    }
