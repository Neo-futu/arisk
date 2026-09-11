"""IRS and swaption products. Priced through the ORE adapter."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class InterestRateSwap(OtcProduct):
    def __post_init__(self) -> None:
        if self.kind not in {ProductKind.IRS, ProductKind.SWAP}:
            self.kind = ProductKind.IRS
        super().__post_init__()


@dataclass
class Swaption(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.SWAPTION
        super().__post_init__()
