"""Equity / listed vanilla option product."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class EquityOption(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.OPTION
        super().__post_init__()
