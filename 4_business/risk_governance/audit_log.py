"""In-memory governance audit trail. Does not create a second master-data store."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        if path is not None and path.exists():
            self.load()

    def record(self, event_type: str, *, actor: str = "system", payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        entry = {
            "event_id": f"aud-{len(self._entries) + 1:06d}",
            "event_type": event_type,
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "payload": dict(payload or {}),
        }
        with self._lock:
            self._entries.append(entry)
            self._persist_unlocked()
        return entry

    def entries(self, event_type: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._entries)
        if event_type:
            return [row for row in rows if row["event_type"] == event_type]
        return rows

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        with self._lock:
            self._entries = list(payload.get("entries") or [])

    def persist(self) -> None:
        with self._lock:
            self._persist_unlocked()

    def _persist_unlocked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


_DEFAULT: AuditLog | None = None


def default_audit() -> AuditLog:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AuditLog()
    return _DEFAULT
