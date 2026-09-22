"""Market data adapter. Vendor SDKs (yfinance / OpenBB) stay here, not in 4_business / 3_riskengine."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..base import ExternalAdapter


class MarketDataAdapter(ExternalAdapter):
    system = "market_data"
    required_permission = "portfolio.view"
    record_type = "MarketQuote"

    def _pull_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "synthetic_panel")
        if mode == "asof_quotes":
            return self._asof_quotes(payload)
        return self._synthetic_panel(payload)

    def _synthetic_panel(self, payload: dict[str, Any]) -> dict[str, Any]:
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

    def _asof_quotes(self, payload: dict[str, Any]) -> dict[str, Any]:
        universe = [str(c).strip() for c in (payload.get("universe") or []) if str(c).strip()]
        as_of = _parse_date(payload.get("as_of")) or date.today()
        lookback = max(int(payload.get("lookback_days") or 14), 1)
        provider = str(payload.get("provider") or "openbb").lower()
        start = as_of - timedelta(days=lookback)

        quotes: dict[str, float] = {}
        quote_dates: dict[str, str] = {}
        warnings: list[str] = []
        missing: list[str] = []

        if provider in {"openbb", "auto"}:
            try:
                for code in universe:
                    row = _openbb_last_close(code, start, as_of)
                    if row is None:
                        missing.append(code)
                        warnings.append(f"{code}: OpenBB 无收盘价")
                        continue
                    quotes[code] = row[0]
                    quote_dates[code] = row[1].isoformat()
            except Exception as exc:  # noqa: BLE001 — vendor optional
                warnings.append(f"OpenBB 不可用: {type(exc).__name__}: {exc}")
                missing = [c for c in universe if c not in quotes]
        else:
            warnings.append(f"未知 provider={provider!r}，未拉取行情")
            missing = list(universe)

        return {
            "mode": "asof_quotes",
            "universe": universe,
            "source": "openbb",
            "provider": provider,
            "as_of": as_of.isoformat(),
            "quotes": quotes,
            "quote_dates": quote_dates,
            "missing": missing,
            "warnings": warnings,
        }


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _openbb_last_close(security_code: str, start: date, end: date) -> tuple[float, date] | None:
    try:
        from openbb import obb
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"openbb not installed: {exc}") from exc

    try:
        frame = obb.equity.price.historical(
            symbol=security_code.strip().upper(),
            provider="yfinance",
            start_date=str(start),
            end_date=str(end),
        ).to_df()
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None
    if "date" in frame.columns:
        frame = frame.set_index("date")
    close_col = "close" if "close" in frame.columns else frame.columns[0]
    series = frame[close_col].dropna()
    if series.empty:
        return None
    last = series.iloc[-1]
    idx = series.index[-1]
    if hasattr(idx, "date"):
        obs = idx.date()
    else:
        obs = _parse_date(idx) or end
    try:
        price = float(last)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price, obs
