"""Redemption coverage: spend most-liquid buckets first (MMF or mixed book)."""
from __future__ import annotations

from typing import Any

from .buckets import BUCKETS, report as bucket_report


def run(bound: Any, redemption_pct: float = 20.0) -> dict[str, Any]:
    snapshot = bound.snapshot
    nav = float(snapshot.net_asset or 0.0)
    need = abs(float(redemption_pct)) / 100.0 * nav
    book = bucket_report(bound)
    remaining = need
    used: list[dict[str, Any]] = []
    for name in BUCKETS:
        available = float(book["buckets"][name]["advancable"])
        take = min(available, remaining)
        used.append({"bucket": name, "available": available, "used": take})
        remaining -= take
        if remaining <= 1e-9:
            remaining = 0.0
            break
    covered = remaining <= 1e-9
    return {
        "analytic": "REDEMPTION",
        "redemption_pct": abs(float(redemption_pct)),
        "redemption_amount": need,
        "covered": covered,
        "shortfall": remaining,
        "coverage_ratio": ((need - remaining) / need) if need else 1.0,
        "waterfall": used,
        "buckets": book["buckets"],
        "ore_app": False,
    }
