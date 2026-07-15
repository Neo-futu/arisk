from __future__ import annotations

import json
import threading
from pathlib import Path

from .core.crypto import canonical_json, sha256_payload
from .schemas import AuditEvent


class AuditLog:
    """Append-only JSONL audit log with a SHA-256 hash chain."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def append(
        self,
        *,
        event_type: str,
        report_id: str,
        actor: str,
        details: dict | None = None,
    ) -> AuditEvent:
        with self._lock:
            events = self._read_unlocked()
            previous_hash = events[-1].event_hash if events else "GENESIS"
            event = AuditEvent(
                sequence=len(events) + 1,
                event_type=event_type,
                report_id=report_id,
                actor=actor,
                details=details or {},
                previous_hash=previous_hash,
            )
            hash_payload = event.model_dump(mode="json", exclude={"event_hash"})
            event.event_hash = sha256_payload(hash_payload)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json(event.model_dump(mode="json")) + "\n")
            return event

    def list(self, *, report_id: str | None = None, limit: int = 200) -> list[AuditEvent]:
        with self._lock:
            events = self._read_unlocked()
        if report_id:
            events = [event for event in events if event.report_id == report_id]
        return events[-limit:]

    def verify(self) -> dict:
        with self._lock:
            events = self._read_unlocked()
        previous_hash = "GENESIS"
        for event in events:
            if event.previous_hash != previous_hash:
                return {"valid": False, "sequence": event.sequence, "reason": "previous_hash mismatch"}
            expected = sha256_payload(event.model_dump(mode="json", exclude={"event_hash"}))
            if event.event_hash != expected:
                return {"valid": False, "sequence": event.sequence, "reason": "event_hash mismatch"}
            previous_hash = event.event_hash
        return {"valid": True, "events": len(events), "head_hash": previous_hash}

    def _read_unlocked(self) -> list[AuditEvent]:
        events: list[AuditEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(AuditEvent.model_validate(json.loads(line)))
        return events
