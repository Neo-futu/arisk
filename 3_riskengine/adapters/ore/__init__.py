"""ORE adapter package."""

from .adapter import ORE_CORE_CALLS, QUANTLIB_CORE_CALLS, OREAdapter
from .trade import descriptor_from_product, trade_from_product

__all__ = [
    "ORE_CORE_CALLS",
    "QUANTLIB_CORE_CALLS",
    "OREAdapter",
    "descriptor_from_product",
    "trade_from_product",
]
