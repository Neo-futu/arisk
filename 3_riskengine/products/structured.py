"""结构化 / 脚本化 OTC。定价走 ORE ``scripted_or_otc``（零冲击=账面）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.contracts import ProductKind
from .otc import OtcProduct


@dataclass
class StructuredNote(OtcProduct):
    """条款驱动的结构化产品。多因子敏感度由 ORE adapter 解析 metadata。"""

    equity_beta: float = 0.5
    rate_duration: float = 1.0
    vol_vega: float = 0.25
    spread_cs01: float = 0.5
    script_id: str = ""

    def __post_init__(self) -> None:
        self.kind = ProductKind.STRUCTURED
        meta = dict(self.metadata or {})
        self.equity_beta = float(meta.get("equity_beta") or self.equity_beta)
        self.rate_duration = float(meta.get("rate_duration") or meta.get("duration") or self.rate_duration)
        self.vol_vega = float(meta.get("vol_vega") or self.vol_vega)
        self.spread_cs01 = float(meta.get("spread_cs01") or self.spread_cs01)
        self.script_id = str(meta.get("script_id") or meta.get("template") or self.script_id or "")
        if self.script_id:
            meta.setdefault("script_id", self.script_id)
            self.metadata = meta
        if not self.tenor_years and self.rate_duration:
            self.tenor_years = float(self.rate_duration)
        super().__post_init__()

    def cashflows(self, market, model=None) -> list[dict[str, Any]]:
        pack = super().cashflows(market, model)
        if pack and pack[0].get("type") == "otc":
            pack[0] = {
                **pack[0],
                "type": "structured",
                "script_id": self.script_id or None,
                "equity_beta": self.equity_beta,
            }
        return pack
