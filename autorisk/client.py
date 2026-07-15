from __future__ import annotations

from typing import Any

import httpx


class AutoRiskClient:
    """Small HTTP SDK for ARISK and third-party callers."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8100",
        api_key: str = "autorisk-dev-key",
        timeout: float = 30.0,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/risk-evals/assess", json=payload)
        response.raise_for_status()
        return response.json()

    def get_report(self, report_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/v1/risk-evals/reports/{report_id}")
        response.raise_for_status()
        return response.json()

    def get_conclusion(self, report_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/v1/risk-evals/reports/{report_id}/conclusion")
        response.raise_for_status()
        return response.json()

    def download_conclusion(self, report_id: str, output_format: str = "json") -> bytes:
        if output_format not in {"json", "html"}:
            raise ValueError("output_format must be 'json' or 'html'")
        response = self._client.get(
            f"/api/v1/risk-evals/reports/{report_id}/conclusion/download",
            params={"format": output_format},
        )
        response.raise_for_status()
        return response.content

    def submit_feedback(
        self,
        report_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/v1/risk-evals/reports/{report_id}/feedback",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_feedback(self, report_id: str, idempotency_key: str) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v1/risk-evals/reports/{report_id}/feedback/{idempotency_key}"
        )
        response.raise_for_status()
        return response.json()

    def list_reports(self, **params: Any) -> dict[str, Any]:
        response = self._client.get("/api/v1/risk-evals/reports", params=params)
        response.raise_for_status()
        return response.json()

    def __enter__(self) -> "AutoRiskClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
