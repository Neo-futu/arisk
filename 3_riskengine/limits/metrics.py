"""Extract limit metrics from an existing ARISK portfolio snapshot."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from ..risk.kpis import (
    kpi_cvar,
    kpi_drawdown,
    kpi_gross_exposure,
    kpi_leverage,
    kpi_liquidity,
    kpi_net_exposure,
    kpi_var,
)

DERIVATIVE_CLASSES = {"FUTURE", "OPTION", "SWAP", "FORWARD", "DERIVATIVE", "FUTURES"}


def _nav(snapshot: Any) -> float:
    return float(snapshot.net_asset or 0.0) or 1.0


def _meta(position: Any, *keys: str, default: str = "") -> str:
    metadata = getattr(position, "metadata", None) or {}
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return default


def issuer_of(position: Any) -> str:
    return _meta(position, "issuer", "issuer_name", default=position.security_name or position.security_code)


def sector_of(position: Any) -> str:
    return _meta(position, "sector", "industry", default=position.asset_class or "UNKNOWN")


def country_of(position: Any) -> str:
    mapped = _meta(position, "country", "region", default="")
    if mapped:
        return mapped
    currency = str(getattr(position, "currency", "") or "")
    return {"HKD": "HK", "USD": "US", "CNY": "CN", "EUR": "EU", "GBP": "GB"}.get(currency, "UNKNOWN")


def counterparty_of(position: Any) -> str:
    return _meta(position, "counterparty", default=issuer_of(position))


def group_ratios(snapshot: Any, key_fn: Callable[[Any], str]) -> dict[str, float]:
    nav = _nav(snapshot)
    buckets: dict[str, float] = defaultdict(float)
    for position in snapshot.positions:
        buckets[key_fn(position)] += abs(float(position.market_value_base))
    return {name: amount / nav for name, amount in buckets.items()}


def position_ratios(snapshot: Any) -> dict[str, float]:
    nav = _nav(snapshot)
    return {p.security_code: abs(float(p.market_value_base)) / nav for p in snapshot.positions}


def currency_ratios(snapshot: Any) -> dict[str, float]:
    return group_ratios(snapshot, lambda p: str(p.currency or snapshot.reporting_currency))


def derivative_ratio(snapshot: Any) -> float:
    nav = _nav(snapshot)
    amount = sum(
        abs(float(p.market_value_base))
        for p in snapshot.positions
        if str(p.asset_class).upper() in DERIVATIVE_CLASSES
    )
    return amount / nav


def _mmf_limit_metrics(snapshot: Any) -> dict[str, float]:
    from ..core.contracts import ProductKind, ViewMode
    from ..products.assemble import products_from_snapshot

    products = products_from_snapshot(snapshot, view=ViewMode.PRODUCT)
    if not products or products[0].kind is not ProductKind.MMF:
        return {"WAM": 0.0, "WAL": 0.0, "Shadow NAV Deviation": 0.0}
    fund = products[0]
    quality = dict(getattr(snapshot, "data_quality", None) or {})
    deviation = quality.get("shadow_deviation_bp") or quality.get("shadow_nav_deviation_bp") or 0.0
    return {
        "WAM": float(fund.wam_days(snapshot.as_of_date)),
        "WAL": float(fund.wal_days(snapshot.as_of_date)),
        "Shadow NAV Deviation": abs(float(deviation)),
    }


def collect_metrics(snapshot: Any) -> dict[str, Any]:
    """Return NAV-ratio metrics used by the Limit Engine."""

    var = kpi_var(snapshot)
    cvar = kpi_cvar(snapshot)
    drawdown = kpi_drawdown(snapshot)
    liquidity = kpi_liquidity(snapshot)
    gross = kpi_gross_exposure(snapshot)
    net = kpi_net_exposure(snapshot)
    leverage = kpi_leverage(snapshot)
    nav = _nav(snapshot)
    var_ratio = abs(float(var["result"]["amount"] or 0.0)) / nav
    cvar_ratio = abs(float(cvar["result"]["amount"] or 0.0)) / nav
    dd = drawdown["result"].get("max_drawdown")
    dd_ratio = abs(float(dd)) if dd is not None else 0.0
    liq_pct = liquidity["result"].get("pct_nav")
    liq_ratio = float(liq_pct) / 100.0 if liq_pct is not None else 0.0
    return {
        "Position": position_ratios(snapshot),
        "Issuer": group_ratios(snapshot, issuer_of),
        "Sector": group_ratios(snapshot, sector_of),
        "Country": group_ratios(snapshot, country_of),
        "Currency": currency_ratios(snapshot),
        "Counterparty": group_ratios(snapshot, counterparty_of),
        "Gross Exposure": float(gross["result"]["ratio"] or 0.0),
        "Net Exposure": abs(float(net["result"]["ratio"] or 0.0)),
        "Leverage": float(leverage["result"]["ratio"] or 0.0),
        "Liquidity": liq_ratio,
        "VaR": var_ratio,
        "CVaR": cvar_ratio,
        "Drawdown": dd_ratio,
        "Derivative Exposure": derivative_ratio(snapshot),
        **_mmf_limit_metrics(snapshot),
    }
