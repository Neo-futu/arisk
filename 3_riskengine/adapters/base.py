"""Adapter protocol shared by FinancePy, Riskfolio and ORE wrappers."""
from __future__ import annotations

from typing import Any, Protocol

from .vendor import VendorProbe


class EngineAdapter(Protocol):
    """Stable adapter surface. Business code never imports vendor packages."""

    name: str

    def initialize(self) -> VendorProbe:
        """Probe vendor availability. Must not raise if the library is missing."""

    @property
    def available(self) -> bool:
        ...

    def describe(self) -> dict[str, Any]:
        ...
