"""Market data adapter. Vendor SDKs (yfinance / OpenBB) stay here, not in 4_business."""
from __future__ import annotations

from typing import Any

from ..base import ExternalAdapter


class MarketDataAdapter(ExternalAdapter):
    system = "market_data"
    required_permission = "portfolio.view"
    record_type = "MarketQuote"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        universe = list(payload.get("universe") or ["AAA", "BBB"])
        from importlib import import_module

        optimizer = import_module("2_processing.tools.performance.portfolio_optimizer")
        lookback = int(payload.get("lookback_days") or 120)
        prices = optimizer.build_synthetic_prices(universe, lookback)
        last = prices.iloc[-1]
        return {
            "universe": universe,
            "source": "synthetic",
            "as_of": str(prices.index[-1].date()),
            "quotes": {str(k): float(last[k]) for k in universe},
        }
