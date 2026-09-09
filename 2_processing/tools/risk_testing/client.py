"""Python/Jupyter client for the authenticated ARISK risk-testing REST API."""
from __future__ import annotations

from typing import Any

import httpx


class RiskTestingClient:
    """Small client usable from Python, IPython, Jupyter and office scripts."""

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.token}

    def capabilities(self) -> dict[str, Any]:
        """Read FinancePy runtime and analytic capabilities."""

        response = httpx.get(
            self.base_url + "/api/v1/fsi/risk-testing/capabilities",
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def scenarios(self) -> list[dict[str, Any]]:
        """Read built-in historical and hypothetical scenarios."""

        response = httpx.get(
            self.base_url + "/api/v1/fsi/risk-testing/catalog",
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["items"]

    def holdings(self, fund_id: str, as_of_date: str) -> dict[str, Any]:
        """Read the authorized current holdings used to build backtest weights."""

        response = httpx.get(
            self.base_url + "/api/v1/fsi/risk-testing/holdings/" + fund_id,
            headers=self._headers,
            params={"as_of_date": as_of_date},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def run(self, fund_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Run one JSON-configured analytic using existing portfolio access."""

        response = httpx.post(
            self.base_url + "/api/v1/fsi/risk-testing/run/" + fund_id,
            headers=self._headers,
            json=request,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def run_xml(self, fund_id: str, configuration: str) -> dict[str, Any]:
        """Run an XML-configured analytic for controlled system integration."""

        response = httpx.post(
            self.base_url + "/api/v1/fsi/risk-testing/run-xml/" + fund_id,
            headers={**self._headers, "Content-Type": "application/xml"},
            content=configuration.encode("utf-8"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
