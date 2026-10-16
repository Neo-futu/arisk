"""Derive LQA-style liquidity fields from holdings and market inputs.

No database access. Callers pass raw book rows plus ADTV / bid-ask parameters.

Bloomberg LQAP structural split:
- Equity / listed volume instruments: horizon from participation × ADTV (depth & breadth).
- Fixed income (bonds / CD): cost and indicative horizon from bid-ask (OTC quote-driven);
  do NOT apply equity participation / ADTV day-splitting. Horizon uses 方案 A ladder:
  ≤10bp→1d, ≤50→3d, ≤150→10d, >150→40d; no quote → uncovered.
- Cash / deposit / repo: contractual / overnight tenor.
"""
from __future__ import annotations

from typing import Any

_PARTICIPATION = 0.10

# Volume / participation path (exchange-like continuous order book).
_VOLUME_HORIZON_ASSETS = frozenset({"EQUITY", "STOCK", "ETF", "FUND", "REIT"})

# Quote-driven FI: bid-ask (and depth) — not ADTV participation.
_FIXED_INCOME_ASSETS = frozenset({"BOND_GOVT", "BOND_CORP", "BOND_FLOAT", "CD"})

# 方案 A 默认阶梯（与 fsi.lqa_fi_horizon_ladder ladder_id=DEFAULT 一致；库表优先）。
# 每项：(max_bid_ask_bps | None 开放上沿, horizon_days)
DEFAULT_FI_HORIZON_LADDER: tuple[tuple[float | None, float], ...] = (
    (10.0, 1.0),
    (50.0, 3.0),
    (150.0, 10.0),
    (None, 40.0),
)

_SECTOR_BASE = {
    "CASH": 98,
    "DEPOSIT": 92,
    "REV_REPO": 88,
    "REPO": 70,
    "BOND_GOVT": 80,
    "CD": 70,
    "BOND_FLOAT": 62,
    "BOND_CORP": 48,
    "EQUITY": 55,
    "STOCK": 55,
    "ETF": 60,
}
_SECTOR_LABEL = {
    "CASH": "Cash",
    "DEPOSIT": "Deposit",
    "REV_REPO": "Reverse Repo",
    "REPO": "Repo",
    "CD": "Certificate of Deposit",
    "BOND_GOVT": "Government",
    "BOND_CORP": "Corporate",
    "BOND_FLOAT": "Floating Rate",
    "EQUITY": "Equity",
    "STOCK": "Equity",
    "ETF": "ETF",
}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _class_for_days(days: float | None) -> str | None:
    if days is None:
        return None
    if days <= 1:
        return "1 day or less"
    if days <= 7:
        return "2-7 days"
    if days <= 30:
        return "8-30 days"
    if days <= 90:
        return "31-90 days"
    if days <= 365:
        return "91-365 days"
    return "Longer than 365 days"


def normalize_fi_horizon_ladder(
    rows: list[tuple[float | None, float]] | tuple[tuple[float | None, float], ...] | None,
) -> tuple[tuple[float | None, float], ...]:
    """Accept DB rows as (max_bid_ask_bps, horizon_days); fall back to DEFAULT."""
    if not rows:
        return DEFAULT_FI_HORIZON_LADDER
    out: list[tuple[float | None, float]] = []
    for max_bps, days in rows:
        out.append((None if max_bps is None else float(max_bps), float(days)))
    return tuple(out) if out else DEFAULT_FI_HORIZON_LADDER


def _fi_horizon_from_bid_ask_bps(
    bps: float | None,
    ladder: tuple[tuple[float | None, float], ...] | None = None,
) -> float | None:
    """方案 A：Bid-Ask（bp）阶梯 → 指示性变现天数。

    权威配置：fsi.lqa_fi_horizon_ladder（ladder_id=DEFAULT）。
    无报价（bps is None）→ None（Not Covered），不查阶梯。
    """
    if bps is None:
        return None
    b = float(bps)
    for max_bps, days in ladder or DEFAULT_FI_HORIZON_LADDER:
        if max_bps is None or b <= max_bps:
            return float(days)
    return None


def _volume_horizon_days(market_value: float, expected_daily_volume: float | None) -> float | None:
    edv = expected_daily_volume or 0.0
    capacity = edv * _PARTICIPATION
    if market_value > 0 and capacity > 0:
        return max(market_value / capacity, 1.0)
    return None


def _liq_horizon_days(
    *,
    asset_category: str,
    market_value: float,
    expected_daily_volume: float | None,
    remaining_days: float | None,
    is_overnight: bool,
    bid_ask_bps: float | None,
    fi_horizon_ladder: tuple[tuple[float | None, float], ...] | None = None,
) -> float | None:
    if asset_category == "CASH":
        return 0.0
    if asset_category == "DEPOSIT":
        return 0.0 if is_overnight else float(max(remaining_days or 0.0, 0.0))
    if asset_category in {"REV_REPO", "REPO"}:
        return float(max(remaining_days if remaining_days is not None else 1.0, 0.0))
    if asset_category in _FIXED_INCOME_ASSETS:
        return _fi_horizon_from_bid_ask_bps(bid_ask_bps, fi_horizon_ladder)
    if asset_category in _VOLUME_HORIZON_ASSETS:
        days = _volume_horizon_days(market_value, expected_daily_volume)
        if days is not None:
            return days
        if remaining_days is not None:
            return float(max(remaining_days, 0.0))
        return None
    # Unknown asset: prefer contractual tenor over equity-style volume split.
    if remaining_days is not None:
        return float(max(remaining_days, 0.0))
    return None


def enrich_position(
    position: dict[str, Any],
    *,
    adtv: dict[str, Any] | None = None,
    bid_ask_bps: float | None = None,
    as_of_date: Any = None,
    fi_horizon_ladder: tuple[tuple[float | None, float], ...] | None = None,
) -> dict[str, Any]:
    """Attach computed LQA fields onto one holding row."""
    asset = str(position.get("asset_category") or "OTHER")
    mv = _num(position.get("market_value")) or 0.0
    duration = _num(position.get("duration"))
    remaining = _num(position.get("remaining_days"))
    overnight = bool(position.get("is_overnight"))
    sample_days = int(_num((adtv or {}).get("sample_days")) or 30)
    adtv_value = _num((adtv or {}).get("adtv_30d"))
    if adtv_value is None or adtv_value <= 0:
        if asset in {"CASH", "DEPOSIT", "REV_REPO"}:
            adtv_value = mv
        else:
            adtv_value = None
    spread_bps = float(bid_ask_bps) if bid_ask_bps is not None else 0.0
    spread = spread_bps / 10000.0
    days = _liq_horizon_days(
        asset_category=asset,
        market_value=mv,
        expected_daily_volume=adtv_value,
        remaining_days=remaining,
        is_overnight=overnight,
        # FI requires an explicit bid-ask; missing config → uncovered (no ADTV fallback).
        bid_ask_bps=bid_ask_bps if asset in _FIXED_INCOME_ASSETS else None,
        fi_horizon_ladder=fi_horizon_ladder,
    )
    sector = position.get("sector") or _SECTOR_LABEL.get(asset, asset)
    base_score = _SECTOR_BASE.get(asset, 40)
    score = max(1.0, min(100.0, base_score - float(days or 0.0) * 0.15))
    vol = 0.0 if not duration or duration <= 0 else duration * 0.01
    if asset in {"CASH", "DEPOSIT", "REV_REPO", "REPO"}:
        horizon_model = "contractual"
    elif asset in _FIXED_INCOME_ASSETS:
        horizon_model = "bid_ask"
    elif asset in _VOLUME_HORIZON_ASSETS:
        horizon_model = "participation"
    else:
        horizon_model = "unknown"
    out = dict(position)
    out.update(
        {
            "price_volatility": vol,
            "expected_daily_volume": adtv_value,
            "bid_ask_spread": spread,
            "spread_bps": spread_bps,
            "sector_score": round(score, 2),
            "liquidity_sector": str(sector),
            "hk_sfc_port_lqdty_class": _class_for_days(days),
            "liq_horizon_days": None if days is None else round(float(days), 2),
            "unif_mkt_imp_cost": spread,
            "empirical_trade_count": sample_days if adtv_value else None,
            "empirical_evaluation_date": as_of_date,
            "empirical_min_trade_volume": adtv_value,
            "empirical_source_date": (adtv or {}).get("adtv_date") or as_of_date,
            "empirical_days_since_last_trade": 0 if adtv_value else None,
            "empirical_avg_trade_volume": adtv_value,
            "empirical_max_trade_volume": adtv_value,
            "empirical_lookback_period": sample_days if adtv_value else None,
            "empirical_total_trade_volume": (adtv_value * sample_days) if adtv_value else None,
            "lqa_source": "COMPUTED",
            "horizon_model": horizon_model,
        }
    )
    return out


def enrich_book(
    positions: list[dict[str, Any]],
    *,
    adtv_by_code: dict[str, dict[str, Any]] | None = None,
    bid_ask_bps_by_asset: dict[str, float] | None = None,
    as_of_date: Any = None,
    fi_horizon_ladder: tuple[tuple[float | None, float], ...] | list[tuple[float | None, float]] | None = None,
) -> list[dict[str, Any]]:
    adtv_map = adtv_by_code or {}
    spread_map = bid_ask_bps_by_asset or {}
    ladder = normalize_fi_horizon_ladder(fi_horizon_ladder)
    return [
        enrich_position(
            row,
            adtv=adtv_map.get(str(row.get("security_code") or "")),
            bid_ask_bps=spread_map.get(str(row.get("asset_category") or "")),
            as_of_date=as_of_date,
            fi_horizon_ladder=ladder,
        )
        for row in positions
    ]
