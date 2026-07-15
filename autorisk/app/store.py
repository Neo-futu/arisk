from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import ValidationError

from .schemas import ExecutionFeedbackReceipt, RiskEvalReport


class FeedbackStoreConflict(ValueError):
    pass


class ReportStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, dict]:
        raw = self.path.read_text(encoding="utf-8").strip() or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, report: RiskEvalReport) -> None:
        with self._lock:
            data = self._read()
            data[report.report_id] = report.model_dump(mode="json")
            self._write(data)

    def get(self, report_id: str) -> RiskEvalReport | None:
        with self._lock:
            data = self._read()
            payload = data.get(report_id)
        if not payload:
            return None
        try:
            return RiskEvalReport.model_validate(payload)
        except ValidationError:
            return None

    def find_by_request_id(self, request_id: str) -> RiskEvalReport | None:
        with self._lock:
            data = self._read()
        for payload in data.values():
            if payload.get("request_id") != request_id:
                continue
            try:
                return RiskEvalReport.model_validate(payload)
            except ValidationError:
                return None
        return None

    def list(self, *, status: str | None = None, fund_code: str | None = None, limit: int = 50) -> list[RiskEvalReport]:
        with self._lock:
            data = self._read()
        reports: list[RiskEvalReport] = []
        for payload in data.values():
            try:
                report = RiskEvalReport.model_validate(payload)
            except ValidationError:
                continue
            if status and report.status.value != status:
                continue
            if fund_code and report.fund_code != fund_code:
                continue
            reports.append(report)
        reports.sort(key=lambda item: item.evaluation_time, reverse=True)
        return reports[:limit]


class FeedbackStore:
    """Persist feedback receipts independently from signed risk reports."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    @staticmethod
    def _key(report_id: str, idempotency_key: str) -> str:
        return f"{report_id}:{idempotency_key}"

    def _read(self) -> dict[str, dict]:
        raw = self.path.read_text(encoding="utf-8").strip() or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def put_if_absent(
        self,
        receipt: ExecutionFeedbackReceipt,
    ) -> tuple[ExecutionFeedbackReceipt, bool]:
        key = self._key(receipt.report_id, receipt.idempotency_key)
        with self._lock:
            data = self._read()
            existing_payload = data.get(key)
            if existing_payload:
                existing = ExecutionFeedbackReceipt.model_validate(existing_payload)
                if existing.feedback_hash != receipt.feedback_hash:
                    raise FeedbackStoreConflict(
                        "Idempotency key already exists with different feedback content"
                    )
                return existing, False
            data[key] = receipt.model_dump(mode="json")
            self._write(data)
        return receipt, True

    def get(
        self,
        report_id: str,
        idempotency_key: str,
    ) -> ExecutionFeedbackReceipt | None:
        key = self._key(report_id, idempotency_key)
        with self._lock:
            payload = self._read().get(key)
        if not payload:
            return None
        try:
            return ExecutionFeedbackReceipt.model_validate(payload)
        except ValidationError:
            return None

    def list(self, report_id: str, limit: int = 100) -> list[ExecutionFeedbackReceipt]:
        prefix = f"{report_id}:"
        with self._lock:
            payloads = [value for key, value in self._read().items() if key.startswith(prefix)]
        receipts: list[ExecutionFeedbackReceipt] = []
        for payload in payloads:
            try:
                receipts.append(ExecutionFeedbackReceipt.model_validate(payload))
            except ValidationError:
                continue
        receipts.sort(key=lambda item: item.received_at, reverse=True)
        return receipts[:limit]
