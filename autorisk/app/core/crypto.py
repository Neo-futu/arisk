from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from enum import Enum
from typing import Any

from ..schemas import AIRecommendation, RiskEvalReport, SignRecord, SignerRole, utc_now


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported value: {type(value)!r}")


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def report_content_hash(report: RiskEvalReport) -> str:
    payload = report.model_dump(mode="json")
    for field in ("content_hash", "artifacts", "first_sign", "second_sign", "updated_at"):
        payload.pop(field, None)
    return sha256_payload(payload)


def create_signature(
    report: RiskEvalReport,
    *,
    signer_id: str,
    signer_role: SignerRole,
    decision: AIRecommendation,
    notes: str,
    secret: str,
) -> SignRecord:
    signed_at = utc_now()
    content_hash = report_content_hash(report)
    material = "|".join(
        [
            report.report_id,
            content_hash,
            signer_id,
            signer_role.value,
            decision.value,
            signed_at.isoformat(),
            notes,
        ]
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        material.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return SignRecord(
        signer_id=signer_id,
        signer_role=signer_role,
        decision=decision,
        signed_at=signed_at,
        notes=notes,
        report_hash=content_hash,
        signature=signature,
    )


def verify_signature(report_id: str, record: SignRecord, secret: str) -> bool:
    material = "|".join(
        [
            report_id,
            record.report_hash,
            record.signer_id,
            record.signer_role.value,
            record.decision.value,
            record.signed_at.isoformat(),
            record.notes,
        ]
    )
    expected = hmac.new(
        secret.encode("utf-8"),
        material.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, record.signature)
