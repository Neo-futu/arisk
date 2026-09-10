"""Trade layer. Instrument ≠ Trade. ORE mapping lands in adapters/ore."""

from ..core.contracts import Trade
from .build import trade_from_product, trades_from_snapshot

__all__ = ["Trade", "trade_from_product", "trades_from_snapshot"]
