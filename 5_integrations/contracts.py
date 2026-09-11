"""ARISK Data Contract for external systems.

External payloads enter here and leave as typed records. This is not a second
holdings master store; Portfolio / Position remain on fsi.balance_*.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


def integrity_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ExternalRecord:
    source: str
    record_type: str
    as_of: date | None
    payload: dict[str, Any]
    integrity: str
    data_quality: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "record_type": self.record_type,
            "as_of": self.as_of.isoformat() if isinstance(self.as_of, date) else self.as_of,
            "payload": self.payload,
            "integrity": self.integrity,
            "data_quality": self.data_quality,
        }


def make_record(source: str, record_type: str, payload: dict[str, Any], *, as_of: date | None = None) -> ExternalRecord:
    body = dict(payload)
    return ExternalRecord(
        source=source,
        record_type=record_type,
        as_of=as_of,
        payload=body,
        integrity=integrity_hash(body),
        data_quality={"source": source, "record_type": record_type, "fields": sorted(body)},
    )


def verify_integrity(record: ExternalRecord | dict[str, Any]) -> bool:
    if isinstance(record, ExternalRecord):
        return record.integrity == integrity_hash(record.payload)
    return str(record.get("integrity") or "") == integrity_hash(record.get("payload") or {})
