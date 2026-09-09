"""Current-holdings historical return backtesting business module."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np

from ..market_data import HistoricalAssetSeries, HistoricalMarketData
from ..models import PortfolioSnapshot
from .common import implemented_by


def _business_dates(start_date: date, end_date: date) -> list[date]:
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _target_weights(
    snapshot: PortfolioSnapshot,
    weight_mode: str,
    custom_weights: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    current_values: dict[str, float] = {}
    for position in snapshot.positions:
        current_values[position.security_code] = (
            current_values.get(position.security_code, 0.0)
            + max(float(position.market_value_base), 0.0)
        )
    current_total = sum(current_values.values())
    if current_total <= 0.0:
        raise ValueError("Portfolio has no positive current holdings for historical backtest")
    current = {code: value / current_total for code, value in current_values.items()}
    if weight_mode == "CURRENT":
        return current, current
    if weight_mode != "CUSTOM":
        raise ValueError("weight_mode must be CURRENT or CUSTOM")

    unknown = sorted(set(custom_weights) - set(current_values))
    if unknown:
        raise ValueError(f"Unknown custom-weight security codes: {', '.join(unknown)}")
    cleaned: dict[str, float] = {}
    for code in current_values:
        value = float(custom_weights.get(code, 0.0))
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"Custom weight for {code} must be a finite non-negative number")
        cleaned[code] = value
    total = sum(cleaned.values())
    if total <= 0.0:
        raise ValueError("Custom weights must contain at least one positive value")
    return current, {code: value / total for code, value in cleaned.items()}


def _series_level(series: HistoricalAssetSeries, value_date: date) -> float | None:
    latest: float | None = None
    for observation_date, value in series.observations:
        if observation_date > value_date:
            break
        latest = value
    return latest


def run(
    snapshot: PortfolioSnapshot,
    market: HistoricalMarketData,
    weight_mode: str = "CURRENT",
    custom_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Replay real historical price paths using current or user-adjusted holdings weights."""

    current_weights, target_weights = _target_weights(
        snapshot,
        weight_mode,
        custom_weights or {},
    )
    series_by_code = {item.security_code: item for item in market.series}
    weighted_series = [
        series_by_code[code]
        for code, weight in target_weights.items()
        if weight > 0.0 and code in series_by_code and series_by_code[code].observations
    ]
    if not weighted_series:
        raise ValueError("No historical market or disclosed proxy series are available")

    effective_start = max(item.observations[0][0] for item in weighted_series)
    effective_start = max(effective_start, market.start_date)
    if effective_start >= market.end_date:
        raise ValueError("Historical series do not contain at least two usable dates in the selected interval")
    calendar = sorted(set(
        _business_dates(effective_start, market.end_date)
        + [
            observation_date
            for item in weighted_series
            for observation_date, _value in item.observations
            if effective_start <= observation_date <= market.end_date
        ]
    ))
    if len(calendar) < 2:
        raise ValueError("Historical backtest requires at least two usable dates")

    initial_capital = float(snapshot.net_asset)
    if initial_capital <= 0.0:
        initial_capital = sum(max(position.market_value_base, 0.0) for position in snapshot.positions)
    initial_levels: dict[str, float] = {}
    units: dict[str, float] = {}
    for code, weight in target_weights.items():
        if weight <= 0.0 or code not in series_by_code:
            continue
        level = _series_level(series_by_code[code], effective_start)
        if level is None or level <= 0.0:
            continue
        initial_levels[code] = level
        units[code] = initial_capital * weight / level

    points: list[dict[str, Any]] = []
    peak = initial_capital
    previous_value: float | None = None
    for value_date in calendar:
        portfolio_value = 0.0
        real_market_value = 0.0
        historical_valuation_value = 0.0
        proxy_value = 0.0
        for code, quantity in units.items():
            series = series_by_code[code]
            level = _series_level(series, value_date)
            if level is None:
                level = initial_levels[code]
            value = quantity * level
            portfolio_value += value
            if series.treatment.startswith("REAL_MARKET"):
                real_market_value += value
            elif series.treatment.startswith("HISTORICAL_VALUATION"):
                historical_valuation_value += value
            else:
                proxy_value += value
        daily_return = (
            portfolio_value / previous_value - 1.0
            if previous_value not in (None, 0.0)
            else 0.0
        )
        peak = max(peak, portfolio_value)
        drawdown = portfolio_value / peak - 1.0 if peak else 0.0
        points.append({
            "date": value_date.isoformat(),
            "portfolio_value": portfolio_value,
            "daily_return_pct": daily_return * 100.0,
            "cumulative_return_pct": (portfolio_value / initial_capital - 1.0) * 100.0,
            "drawdown_pct": drawdown * 100.0,
            "real_market_value": real_market_value,
            "historical_valuation_value": historical_valuation_value,
            "proxy_value": proxy_value,
        })
        previous_value = portfolio_value

    ending_value = points[-1]["portfolio_value"]
    pnl = ending_value - initial_capital
    total_return = ending_value / initial_capital - 1.0 if initial_capital else 0.0
    elapsed_days = max((calendar[-1] - calendar[0]).days, 1)
    annualized_return = (
        (ending_value / initial_capital) ** (365.0 / elapsed_days) - 1.0
        if initial_capital > 0.0 and ending_value > 0.0
        else None
    )
    daily_returns = np.asarray([point["daily_return_pct"] / 100.0 for point in points[1:]], dtype=float)
    annualized_volatility = (
        float(np.std(daily_returns, ddof=1) * np.sqrt(252.0))
        if daily_returns.size >= 2
        else 0.0
    )
    max_drawdown = min(point["drawdown_pct"] for point in points)

    position_results: list[dict[str, Any]] = []
    for code, target_weight in sorted(target_weights.items(), key=lambda item: item[1], reverse=True):
        series = series_by_code.get(code)
        if series is None or code not in initial_levels:
            continue
        ending_level = _series_level(series, calendar[-1]) or initial_levels[code]
        start_allocation = initial_capital * target_weight
        ending_allocation = units[code] * ending_level
        position_results.append({
            "security_code": code,
            "security_name": series.security_name,
            "asset_class": series.asset_class,
            "current_weight_pct": current_weights.get(code, 0.0) * 100.0,
            "target_weight_pct": target_weight * 100.0,
            "start_level": initial_levels[code],
            "end_level": ending_level,
            "asset_return_pct": (ending_level / initial_levels[code] - 1.0) * 100.0,
            "pnl": ending_allocation - start_allocation,
            "source": series.source,
            "treatment": series.treatment,
        })

    real_weight = sum(
        target_weights.get(item.security_code, 0.0)
        for item in market.series
        if item.treatment.startswith("REAL_MARKET")
    )
    historical_valuation_weight = sum(
        target_weights.get(item.security_code, 0.0)
        for item in market.series
        if item.treatment.startswith("HISTORICAL_VALUATION")
    )
    proxy_weight = max(1.0 - real_weight - historical_valuation_weight, 0.0)
    report: dict[str, Any] = {
        "analytic": "HISTORICAL_BACKTEST",
        "engine": "ARISK Historical Market Backtest",
        "library": "NumPy",
        "fund_id": snapshot.fund_id,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "start_date": market.start_date.isoformat(),
        "end_date": market.end_date.isoformat(),
        "effective_start_date": calendar[0].isoformat(),
        "reporting_currency": snapshot.reporting_currency,
        "net_asset": snapshot.net_asset,
        "weight_mode": weight_mode,
        "initial_value": initial_capital,
        "ending_value": ending_value,
        "pnl": pnl,
        "pnl_pct_nav": pnl / snapshot.net_asset * 100.0 if snapshot.net_asset else None,
        "total_return_pct": total_return * 100.0,
        "annualized_return_pct": annualized_return * 100.0 if annualized_return is not None else None,
        "annualized_volatility_pct": annualized_volatility * 100.0,
        "max_drawdown_pct": max_drawdown,
        "observation_count": len(points),
        "backtest_points": points,
        "position_results": position_results,
        "data_quality": {
            **snapshot.data_quality,
            "requested_start_date": market.start_date.isoformat(),
            "effective_start_date": calendar[0].isoformat(),
            "end_date": market.end_date.isoformat(),
            "real_market_weight_pct": real_weight * 100.0,
            "historical_valuation_weight_pct": historical_valuation_weight * 100.0,
            "proxy_weight_pct": proxy_weight * 100.0,
            "historical_series_count": len(market.series),
            "market_data_sources": list(market.source_tables),
            "series_sources": [
                {
                    "security_code": item.security_code,
                    "source": item.source,
                    "treatment": item.treatment,
                    "observation_count": len(item.observations),
                }
                for item in market.series
            ],
        },
        "assumptions": [
            "以所选结束时点的当前持仓作为历史回测投资范围，不使用历史持仓变化。",
            "区间首个可用日按目标权重建仓，之后采用买入持有法，权重随市场价格自然漂移。",
            "优先使用真实市场行情；缺少市场行情时依次使用历史持仓单位估值、应计收益或零收益代理并披露覆盖率。",
            "非本位币资产优先使用历史即期汇率换算；缺失时使用持仓快照汇率并明确标记。",
            "结果未计交易成本、税费、申赎、票息现金再投资及组合管理人的历史交易行为。",
        ],
    }
    return implemented_by(
        report,
        "risk_testing.analytics.historical_backtest.run",
        [],
        "real-market total-return replay with disclosed valuation/accrual fallbacks",
    )
