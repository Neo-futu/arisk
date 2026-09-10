"""SFC MMF compliance 口径. SQL remains input; this is the status function."""
from __future__ import annotations

from typing import Any, Literal

Status = Literal["ok", "warn", "breach"]

SFC_WAM_LIMIT_DAYS = 60.0
SFC_WAL_LIMIT_DAYS = 120.0
DEVIATION_BREACH_BP = 50.0
DEVIATION_WARN_BP = 40.0
LIMIT_WARN_RATIO = 0.9


def compliance_status(
    is_mmf: bool,
    wam_days: float | None,
    wal_days: float | None,
    wam_limit: float | None,
    wal_limit: float | None,
    deviation_bp: float | None,
) -> Status:
    """Derive an MMF cockpit status. Non-MMF (or no metrics) → ok.

    breach: any hard SFC limit exceeded (WAM>limit, WAL>limit, |deviation|>50bp).
    warn:   nearing a limit (≥90% of WAM/WAL limit, or |deviation|≥40bp).
    """

    if not is_mmf:
        return "ok"
    breach = False
    warn = False
    for value, limit in ((wam_days, wam_limit), (wal_days, wal_limit)):
        if value is None or limit is None or limit <= 0:
            continue
        if value > limit:
            breach = True
        elif value >= limit * LIMIT_WARN_RATIO:
            warn = True
    if deviation_bp is not None:
        abs_dev = abs(deviation_bp)
        if abs_dev > DEVIATION_BREACH_BP:
            breach = True
        elif abs_dev >= DEVIATION_WARN_BP:
            warn = True
    if breach:
        return "breach"
    if warn:
        return "warn"
    return "ok"


def report(
    *,
    is_mmf: bool,
    wam_days: float | None,
    wal_days: float | None,
    wam_limit: float | None = SFC_WAM_LIMIT_DAYS,
    wal_limit: float | None = SFC_WAL_LIMIT_DAYS,
    deviation_bp: float | None = None,
) -> dict[str, Any]:
    status = compliance_status(is_mmf, wam_days, wal_days, wam_limit, wal_limit, deviation_bp)
    return {
        "is_mmf": bool(is_mmf),
        "wam_days": wam_days,
        "wal_days": wal_days,
        "wam_limit": wam_limit,
        "wal_limit": wal_limit,
        "shadow_deviation_bp": deviation_bp,
        "status": status,
        "source": "3_riskengine.limits.sfc",
    }
