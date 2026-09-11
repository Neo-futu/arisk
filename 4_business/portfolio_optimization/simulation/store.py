"""In-memory / file-backed Simulation Portfolio store.

Live Portfolio → Clone → Simulation Portfolio → Modify → Optimize → Stress → Compare

Never writes fsi.balance_*. Unauthorized callers cannot modify a live snapshot.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from ..snapshots import apply_weights, clone_snapshot, current_weights, snapshot_from_weights


class LivePortfolioLocked(PermissionError):
    """Raised when a caller tries to mutate a live portfolio without authorization."""


class SimulationStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            self.load()

    def clone_live(
        self,
        snapshot: Any,
        *,
        label: str = "",
        authorized_live_write: bool = False,
    ) -> dict[str, Any]:
        del authorized_live_write  # clone never writes live holdings
        sim_id = f"sim-{uuid.uuid4().hex[:12]}"
        cloned = clone_snapshot(snapshot, fund_id=sim_id)
        record = {
            "sim_id": sim_id,
            "kind": "simulation",
            "label": label,
            "live_fund_id": snapshot.fund_id,
            "as_of_date": snapshot.as_of_date.isoformat()
            if isinstance(snapshot.as_of_date, date)
            else str(snapshot.as_of_date),
            "reporting_currency": snapshot.reporting_currency,
            "net_asset": snapshot.net_asset,
            "live_weights": current_weights(snapshot),
            "weights": current_weights(snapshot),
            "snapshot": cloned,
            "live_snapshot": snapshot,
            "reviews": [],
            "stress": None,
        }
        with self._lock:
            self._records[sim_id] = record
            self._persist_unlocked()
        return self.public(record)

    def get(self, sim_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(sim_id)
        if record is None:
            raise KeyError(sim_id)
        return record

    def modify(
        self,
        sim_id: str,
        weights: Mapping[str, float],
        *,
        target: str = "simulation",
        authorized: bool = False,
    ) -> dict[str, Any]:
        if target == "live":
            self._reject_live_write(authorized)
        record = self.get(sim_id)
        record["snapshot"] = apply_weights(record["snapshot"], weights)
        record["weights"] = dict(weights)
        with self._lock:
            self._records[sim_id] = record
            self._persist_unlocked()
        return self.public(record)

    def attach_review(self, sim_id: str, review: Mapping[str, Any]) -> dict[str, Any]:
        record = self.get(sim_id)
        record["reviews"] = list(record.get("reviews") or []) + [dict(review)]
        if review.get("weights"):
            record["weights"] = dict(review["weights"])
            record["snapshot"] = apply_weights(record["live_snapshot"], review["weights"])
        with self._lock:
            self._records[sim_id] = record
            self._persist_unlocked()
        return self.public(record)

    def attach_stress(self, sim_id: str, stress: Mapping[str, Any]) -> dict[str, Any]:
        record = self.get(sim_id)
        record["stress"] = dict(stress)
        with self._lock:
            self._records[sim_id] = record
            self._persist_unlocked()
        return self.public(record)

    def apply_to_live(self, sim_id: str, *, authorized: bool = False) -> dict[str, Any]:
        self.get(sim_id)
        self._reject_live_write(authorized)
        return {
            "sim_id": sim_id,
            "live_modified": False,
            "is_trade_instruction": False,
            "status": "AUTHORIZED_PROPOSAL",
            "next": "portfolio_management",
            "detail": "Even an authorized proposal does not write fsi.balance_*; live changes go through portfolio_management.",
        }

    def compare(self, sim_id: str) -> dict[str, Any]:
        record = self.get(sim_id)
        live = record["live_weights"]
        sim = record["weights"]
        keys = sorted(set(live) | set(sim))
        return {
            "sim_id": sim_id,
            "live_fund_id": record["live_fund_id"],
            "live_weights": live,
            "sim_weights": sim,
            "weight_diff": {k: float(sim.get(k, 0.0)) - float(live.get(k, 0.0)) for k in keys},
            "turnover": 0.5 * sum(abs(float(sim.get(k, 0.0)) - float(live.get(k, 0.0))) for k in keys),
            "latest_review_status": (record["reviews"][-1].get("status") if record["reviews"] else None),
            "stress": record.get("stress"),
            "is_trade_instruction": False,
        }

    def persist(self) -> None:
        with self._lock:
            self._persist_unlocked()

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        records: dict[str, dict[str, Any]] = {}
        for item in payload.get("simulations", []):
            weights = item["weights"]
            snapshot = snapshot_from_weights(
                weights,
                fund_id=item["sim_id"],
                nav=float(item.get("net_asset") or 1_000_000.0),
                reporting_currency=item.get("reporting_currency") or "HKD",
            )
            live_weights = item.get("live_weights") or weights
            records[item["sim_id"]] = {
                **item,
                "snapshot": snapshot,
                "live_snapshot": snapshot_from_weights(
                    live_weights,
                    fund_id=item.get("live_fund_id") or "LIVE",
                    nav=float(item.get("net_asset") or 1_000_000.0),
                    reporting_currency=item.get("reporting_currency") or "HKD",
                ),
            }
        with self._lock:
            self._records = records

    def public(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "sim_id": record["sim_id"],
            "kind": "simulation",
            "label": record.get("label") or "",
            "live_fund_id": record["live_fund_id"],
            "as_of_date": record["as_of_date"],
            "net_asset": record["net_asset"],
            "weights": dict(record["weights"]),
            "live_weights": dict(record["live_weights"]),
            "is_live": False,
            "is_trade_instruction": False,
            "review_count": len(record.get("reviews") or []),
        }

    def _reject_live_write(self, authorized: bool) -> None:
        if not authorized:
            raise LivePortfolioLocked("未经授权不得修改 Live Portfolio")

    def _persist_unlocked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "simulations": [
                {
                    "sim_id": rec["sim_id"],
                    "kind": "simulation",
                    "label": rec.get("label") or "",
                    "live_fund_id": rec["live_fund_id"],
                    "as_of_date": rec["as_of_date"],
                    "reporting_currency": rec["reporting_currency"],
                    "net_asset": rec["net_asset"],
                    "live_weights": rec["live_weights"],
                    "weights": rec["weights"],
                    "reviews": rec.get("reviews") or [],
                    "stress": rec.get("stress"),
                }
                for rec in self._records.values()
            ]
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


_DEFAULT: SimulationStore | None = None


def default_store() -> SimulationStore:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SimulationStore()
    return _DEFAULT
