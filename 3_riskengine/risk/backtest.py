"""Historical return backtest. Buy-and-hold on NAV or duck-typed market series."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping

import numpy as np

from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..market.snapshot import data_quality, nav_observations


def _business_dates(start_date: date, end_date: date) -> list[date]:
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _weights(snapshot: Any, weight_mode: str, custom_weights: Mapping[str, float] | None) -> dict[str, float]:
    values: dict[str, float] = {}
    for position in snapshot.positions:
        values[position.security_code] = values.get(position.security_code, 0.0) + max(
            float(position.market_value_base), 0.0
        )
    total = sum(values.values())
    if total <= 0:
        raise ValueError("Portfolio has no positive holdings for historical backtest")
    current = {code: value / total for code, value in values.items()}
    if weight_mode == "CURRENT":
        return current
    cleaned = {code: float((custom_weights or {}).get(code, 0.0)) for code in current}
    mass = sum(cleaned.values())
    if mass <= 0:
        raise ValueError("Custom weights must contain at least one positive value")
    return {code: value / mass for code, value in cleaned.items()}


def _series_level(observations: list[tuple[date, float]], value_date: date) -> float | None:
    latest: float | None = None
    for observation_date, value in observations:
        if observation_date > value_date:
            break
        latest = value
    return latest


def _nav_path(bound: Any) -> dict[str, Any]:
    snapshot = bound.snapshot
    observations = nav_observations(snapshot)
    nav = float(snapshot.net_asset or 0.0)
    if len(observations) < 2 or nav <= 0:
        return {
            "analytic": "HISTORICAL_BACKTEST",
            "status": "INSUFFICIENT_DATA",
            "backtest_points": [],
            "observation_count": len(observations),
        }
    wealth = nav
    peak = nav
    points = []
    previous = None
    for as_of, ret in observations:
        wealth = wealth * (1.0 + float(ret)) if previous is not None else nav
        peak = max(peak, wealth)
        daily = float(ret) if previous is not None else 0.0
        points.append(
            {
                "date": as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of),
                "portfolio_value": wealth,
                "daily_return_pct": daily * 100.0,
                "cumulative_return_pct": (wealth / nav - 1.0) * 100.0,
                "drawdown_pct": (wealth / peak - 1.0) * 100.0 if peak else 0.0,
            }
        )
        previous = wealth
    ending = points[-1]["portfolio_value"]
    daily = np.asarray([item["daily_return_pct"] / 100.0 for item in points[1:]], dtype=float)
    vol = float(np.std(daily, ddof=1) * np.sqrt(252.0)) if daily.size >= 2 else 0.0
    return {
        "analytic": "HISTORICAL_BACKTEST",
        "status": "OK",
        "weight_mode": "CURRENT",
        "initial_value": nav,
        "ending_value": ending,
        "pnl": ending - nav,
        "pnl_pct_nav": (ending - nav) / nav * 100.0,
        "total_return_pct": (ending / nav - 1.0) * 100.0,
        "annualized_volatility_pct": vol * 100.0,
        "max_drawdown_pct": min(item["drawdown_pct"] for item in points),
        "observation_count": len(points),
        "backtest_points": points,
        "path": "nav_returns",
    }


def _market_path(
    bound: Any,
    market: Any,
    weight_mode: str,
    custom_weights: Mapping[str, float] | None,
) -> dict[str, Any]:
    snapshot = bound.snapshot
    target = _weights(snapshot, weight_mode, custom_weights)
    series_by_code = {item.security_code: item for item in market.series}
    weighted = [
        series_by_code[code]
        for code, weight in target.items()
        if weight > 0.0 and code in series_by_code and getattr(series_by_code[code], "observations", None)
    ]
    if not weighted:
        raise ValueError("No historical market series are available")
    effective_start = max(item.observations[0][0] for item in weighted)
    effective_start = max(effective_start, market.start_date)
    calendar = sorted(
        set(
            _business_dates(effective_start, market.end_date)
            + [
                observation_date
                for item in weighted
                for observation_date, _value in item.observations
                if effective_start <= observation_date <= market.end_date
            ]
        )
    )
    if len(calendar) < 2:
        raise ValueError("Historical backtest requires at least two usable dates")
    initial_capital = float(snapshot.net_asset or 0.0) or sum(
        max(float(p.market_value_base), 0.0) for p in snapshot.positions
    )
    initial_levels: dict[str, float] = {}
    units: dict[str, float] = {}
    for code, weight in target.items():
        if weight <= 0.0 or code not in series_by_code:
            continue
        level = _series_level(list(series_by_code[code].observations), effective_start)
        if level is None or level <= 0.0:
            continue
        initial_levels[code] = level
        units[code] = initial_capital * weight / level
    points: list[dict[str, Any]] = []
    peak = initial_capital
    previous_value: float | None = None
    for value_date in calendar:
        portfolio_value = 0.0
        for code, quantity in units.items():
            series = series_by_code[code]
            level = _series_level(list(series.observations), value_date) or initial_levels[code]
            portfolio_value += quantity * level
        daily_return = portfolio_value / previous_value - 1.0 if previous_value not in (None, 0.0) else 0.0
        peak = max(peak, portfolio_value)
        points.append(
            {
                "date": value_date.isoformat(),
                "portfolio_value": portfolio_value,
                "daily_return_pct": daily_return * 100.0,
                "cumulative_return_pct": (portfolio_value / initial_capital - 1.0) * 100.0,
                "drawdown_pct": (portfolio_value / peak - 1.0) * 100.0 if peak else 0.0,
            }
        )
        previous_value = portfolio_value
    ending = points[-1]["portfolio_value"]
    daily = np.asarray([item["daily_return_pct"] / 100.0 for item in points[1:]], dtype=float)
    vol = float(np.std(daily, ddof=1) * np.sqrt(252.0)) if daily.size >= 2 else 0.0
    elapsed = max((calendar[-1] - calendar[0]).days, 1)
    annualized = (ending / initial_capital) ** (365.0 / elapsed) - 1.0 if initial_capital > 0 and ending > 0 else None
    return {
        "analytic": "HISTORICAL_BACKTEST",
        "status": "OK",
        "weight_mode": weight_mode,
        "start_date": market.start_date.isoformat(),
        "end_date": market.end_date.isoformat(),
        "effective_start_date": calendar[0].isoformat(),
        "initial_value": initial_capital,
        "ending_value": ending,
        "pnl": ending - initial_capital,
        "pnl_pct_nav": (ending - initial_capital) / snapshot.net_asset * 100.0 if snapshot.net_asset else None,
        "total_return_pct": (ending / initial_capital - 1.0) * 100.0,
        "annualized_return_pct": annualized * 100.0 if annualized is not None else None,
        "annualized_volatility_pct": vol * 100.0,
        "max_drawdown_pct": min(item["drawdown_pct"] for item in points),
        "observation_count": len(points),
        "backtest_points": points,
        "path": "market_series",
    }


def run(
    bound: Any,
    *,
    market: Any | None = None,
    weight_mode: str = "CURRENT",
    custom_weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    payload = _market_path(bound, market, weight_mode, custom_weights) if market is not None else _nav_path(bound)
    snapshot = bound.snapshot
    payload.setdefault("engine", RISKENGINE_NAME)
    payload.setdefault("engine_version", RISKENGINE_VERSION)
    payload.setdefault("fund_id", getattr(snapshot, "fund_id", ""))
    payload.setdefault("as_of_date", snapshot.as_of_date.isoformat())
    payload.setdefault("reporting_currency", snapshot.reporting_currency)
    payload.setdefault("net_asset", snapshot.net_asset)
    payload.setdefault("data_quality", data_quality(snapshot, path=payload.get("path")))
    payload.setdefault("library", "NumPy")
    payload.setdefault("ore_app", False)
    return payload
