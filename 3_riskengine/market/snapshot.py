"""Market views over an existing ARISK portfolio snapshot."""
from __future__ import annotations

from typing import Any

import numpy as np


def nav_returns(snapshot: Any) -> np.ndarray:
    return np.asarray([item[1] for item in getattr(snapshot, "nav_returns", ()) or ()], dtype=float)


def nav_observations(snapshot: Any) -> list[tuple[Any, float]]:
    return list(getattr(snapshot, "nav_returns", ()) or ())


def equity_volatilities(snapshot: Any) -> dict[str, float]:
    vols: dict[str, float] = {}
    for position in snapshot.positions:
        metadata = getattr(position, "metadata", None) or {}
        vol = metadata.get("historical_volatility")
        if vol is not None:
            vols[str(position.security_code)] = float(vol)
    return vols


def reporting_currency(snapshot: Any) -> str:
    return str(getattr(snapshot, "reporting_currency", "HKD") or "HKD")


def data_quality(snapshot: Any, **extra: Any) -> dict[str, Any]:
    payload = dict(getattr(snapshot, "data_quality", {}) or {})
    payload.update(extra)
    payload.setdefault("source_tables", ["fsi.balance_*", "fsi.mktdata_*"])
    payload.setdefault("position_count", len(getattr(snapshot, "positions", ()) or ()))
    payload.setdefault("nav", getattr(snapshot, "net_asset", None))
    return payload
