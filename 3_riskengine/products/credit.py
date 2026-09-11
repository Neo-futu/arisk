"""Credit default swap product. Priced through the ORE adapter."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class CreditDefaultSwap(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.CDS
        super().__post_init__()
