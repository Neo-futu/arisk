"""Default risk-appetite / limit catalog.

Values are NAV ratios unless noted. Defaults are intentionally loose so the
shared sample snapshot stays GREEN; tests inject a tighter policy for breaches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LIMIT_IDS = (
    "Position",
    "Issuer",
    "Sector",
    "Country",
    "Currency",
    "Counterparty",
    "Gross Exposure",
    "Net Exposure",
    "Leverage",
    "Liquidity",
    "VaR",
    "CVaR",
    "Drawdown",
    "Derivative Exposure",
    "WAM",
    "WAL",
    "Shadow NAV Deviation",
)


@dataclass(frozen=True)
class LimitSpec:
    limit_id: str
    direction: str  # MAX | MIN
    limit: float
    warning: float = 0.8
    hard: float = 1.1
    unit: str = "ratio"
    grouped: bool = False


DEFAULT_SPECS: tuple[LimitSpec, ...] = (
    LimitSpec("Position", "MAX", 1.0, grouped=True),
    LimitSpec("Issuer", "MAX", 1.0, grouped=True),
    LimitSpec("Sector", "MAX", 1.0, grouped=True),
    LimitSpec("Country", "MAX", 1.0, grouped=True),
    LimitSpec("Currency", "MAX", 1.0, grouped=True),
    LimitSpec("Counterparty", "MAX", 1.0, grouped=True),
    LimitSpec("Gross Exposure", "MAX", 2.0),
    LimitSpec("Net Exposure", "MAX", 2.0),
    LimitSpec("Leverage", "MAX", 2.0),
    LimitSpec("Liquidity", "MIN", 0.0, warning=0.8, hard=1.1),
    LimitSpec("VaR", "MAX", 0.50),
    LimitSpec("CVaR", "MAX", 0.50),
    LimitSpec("Drawdown", "MAX", 0.80),
    LimitSpec("Derivative Exposure", "MAX", 0.50),
    LimitSpec("WAM", "MAX", 60.0, warning=0.9, hard=1.1, unit="days"),
    LimitSpec("WAL", "MAX", 120.0, warning=0.9, hard=1.1, unit="days"),
    LimitSpec("Shadow NAV Deviation", "MAX", 50.0, warning=0.8, hard=1.1, unit="bp"),
)


def policy_from_overrides(overrides: dict[str, Any] | None = None) -> dict[str, LimitSpec]:
    specs = {spec.limit_id: spec for spec in DEFAULT_SPECS}
    for limit_id, raw in (overrides or {}).items():
        if limit_id not in specs:
            continue
        base = specs[limit_id]
        if isinstance(raw, (int, float)):
            specs[limit_id] = LimitSpec(
                limit_id=base.limit_id,
                direction=base.direction,
                limit=float(raw),
                warning=base.warning,
                hard=base.hard,
                unit=base.unit,
                grouped=base.grouped,
            )
            continue
        if isinstance(raw, dict):
            specs[limit_id] = LimitSpec(
                limit_id=base.limit_id,
                direction=str(raw.get("direction") or base.direction),
                limit=float(raw.get("limit", base.limit)),
                warning=float(raw.get("warning", base.warning)),
                hard=float(raw.get("hard", base.hard)),
                unit=str(raw.get("unit") or base.unit),
                grouped=base.grouped,
            )
    return specs


def spec_as_dict(spec: LimitSpec) -> dict[str, Any]:
    return {
        "limit_id": spec.limit_id,
        "direction": spec.direction,
        "limit": spec.limit,
        "warning": spec.warning,
        "hard": spec.hard,
        "unit": spec.unit,
        "grouped": spec.grouped,
    }
