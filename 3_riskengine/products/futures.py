"""Listed future product."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class Future(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.FUTURE
        super().__post_init__()
