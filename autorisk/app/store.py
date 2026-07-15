from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import ValidationError

from .schemas import RiskEvalReport


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
