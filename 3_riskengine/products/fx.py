"""FX spot, forward and option products."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class FxSpot(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.FX
        super().__post_init__()


@dataclass
class FxForward(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.FX_FORWARD
        super().__post_init__()


@dataclass
class FxOption(OtcProduct):
    def __post_init__(self) -> None:
        self.kind = ProductKind.FX_OPTION
        super().__post_init__()
