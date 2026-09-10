"""Risk Testing analytics on BoundRiskEngine. Vendors stay in adapters."""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import numpy as np

from ..core.contracts import RiskFactorType, Shock, ShockMode
from ..core.lineage import DEFAULT_ASSUMPTIONS, RISKENGINE_NAME, RISKENGINE_VERSION
from ..instruments.classify import KRD_BUCKETS
from ..instruments.shocks import scale_shocks, shock_as_dict
from ..market.snapshot import data_quality, nav_observations, nav_returns

TESTING_ANALYTICS: tuple[str, ...] = (
    "SENSITIVITY",
    "STRESS",
    "SCENARIO",
    "REVERSE_STRESS",
    "TAIL_RISK",
    "KRD",
    "PNL_EXPLAIN",
    "HISTORICAL_BACKTEST",
    "VAR_BACKTEST",
    "XVA",
)


def stamp(bound: Any, analytic: str, payload: dict[str, Any], *, model: str) -> dict[str, Any]:
    snapshot = bound.snapshot
    report = {
        "analytic": analytic,
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "platform_engine": RISKENGINE_NAME,
        "model": model,
        "model_version": RISKENGINE_VERSION,
        "fund_id": getattr(snapshot, "fund_id", ""),
        "as_of_date": snapshot.as_of_date.isoformat(),
        "reporting_currency": snapshot.reporting_currency,
        "net_asset": snapshot.net_asset,
        "data_quality": data_quality(snapshot),
        "assumptions": list(DEFAULT_ASSUMPTIONS),
        "adapters": bound.engine.adapters_status(),
        **payload,
    }
    report["analytic"] = analytic
    report["engine"] = RISKENGINE_NAME
    report["engine_version"] = RISKENGINE_VERSION
    report.setdefault("valuation_date", snapshot.as_of_date.isoformat())
    report.setdefault("market_data_date", snapshot.as_of_date.isoformat())
    return report


def revalue_pack(bound: Any, shocks: Iterable[Any] = ()) -> dict[str, Any]:
    result = bound.valuation().revalue(tuple(shocks))
    return {
        "base_pv": result.base_pv,
        "shocked_pv": result.shocked_pv,
        "pnl": result.pnl,
        "pnl_pct_nav": result.pnl_pct_nav,
        "trade_values": result.trade_values,
    }


def sensitivity(bound: Any, shocks: Iterable[Any]) -> dict[str, Any]:
    report = bound.valuation().greeks(tuple(shocks))
    return stamp(bound, "SENSITIVITY", report, model="product_market_model")


def scenario(bound: Any, scenario_def: Any) -> dict[str, Any]:
    pack = revalue_pack(bound, scenario_def.shocks)
    book = bound.portfolio().aggregate(shocks=tuple(scenario_def.shocks))
    return stamp(
        bound,
        "SCENARIO",
        {
            "scenario": {
                "scenario_id": scenario_def.scenario_id,
                "name": scenario_def.name,
                "category": scenario_def.category,
                "description": getattr(scenario_def, "description", ""),
                "shocks": [shock_as_dict(item) for item in scenario_def.shocks],
            },
            "by_asset_class": book["by_asset_class"],
            "ore_app": False,
            **pack,
        },
        model="product_revalue",
    )


def stress(bound: Any, scenario_def: Any) -> dict[str, Any]:
    report = scenario(bound, scenario_def)
    report["analytic"] = "STRESS"
    report["ore_adapter"] = bound.engine.ore.describe()
    report["model"] = "product_revalue_stress"
    return report


def reverse_stress(
    bound: Any,
    scenario_def: Any,
    target_loss_pct_nav: float,
    max_scale: float = 20.0,
) -> dict[str, Any]:
    nav = float(bound.snapshot.net_asset or 0.0)
    target_loss = abs(target_loss_pct_nav) / 100.0 * nav
    low, high = 0.0, max_scale
    high_result = revalue_pack(bound, scale_shocks(scenario_def.shocks, high))
    reached = -high_result["pnl"] >= target_loss
    iterations = 0
    if reached:
        for _ in range(60):
            iterations += 1
            middle = (low + high) / 2.0
            result = revalue_pack(bound, scale_shocks(scenario_def.shocks, middle))
            if -result["pnl"] >= target_loss:
                high = middle
            else:
                low = middle
        final = revalue_pack(bound, scale_shocks(scenario_def.shocks, high))
    else:
        final = high_result
    return stamp(
        bound,
        "REVERSE_STRESS",
        {
            "scenario_id": scenario_def.scenario_id,
            "target_loss_pct_nav": abs(target_loss_pct_nav),
            "target_loss_amount": target_loss,
            "breach_reached": reached,
            "critical_scale": high if reached else None,
            "tested_max_scale": max_scale,
            "iterations": iterations,
            "critical_shocks": [shock_as_dict(item) for item in scale_shocks(scenario_def.shocks, high)],
            **final,
        },
        model="product_revalue",
    )


def tail_risk(bound: Any, sigma_levels: Iterable[float], capital_buffer: float) -> dict[str, Any]:
    returns = nav_returns(bound.snapshot)
    if returns.size < 2:
        return stamp(bound, "TAIL_RISK", {"status": "INSUFFICIENT_DATA", "tail_scenarios": []}, model="riskfolio_nav")
    pack = bound.engine.riskfolio.historical_var_cvar(returns, 0.99)
    mean = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    var_return = float(pack["var"]) if pack.get("var") is not None else float(np.percentile(returns, 1.0))
    expected_shortfall = float(pack["cvar"]) if pack.get("cvar") is not None else var_return
    nav = float(bound.snapshot.net_asset or 0.0)
    scenarios = []
    for level in sigma_levels:
        shock_return = mean - abs(level) * sigma
        loss = max(-shock_return * nav, 0.0)
        scenarios.append(
            {
                "sigma": abs(level),
                "shock_return_pct": shock_return * 100.0,
                "loss_amount": loss,
                "loss_pct_nav": (loss / nav * 100.0) if nav else None,
                "capital_after": capital_buffer - loss,
                "capital_adequacy_pct": ((capital_buffer - loss) / nav * 100.0) if nav else None,
                "capital_breached": loss > capital_buffer,
            }
        )
    return stamp(
        bound,
        "TAIL_RISK",
        {
            "status": "OK",
            "sample_size": int(returns.size),
            "daily_mean_pct": mean * 100.0,
            "daily_volatility_pct": sigma * 100.0,
            "historical_var_99_amount": abs(var_return * nav),
            "expected_shortfall_99_amount": abs(expected_shortfall * nav),
            "tail_scenarios": scenarios,
            "library": pack.get("engine"),
        },
        model="riskfolio_nav",
    )


def krd(bound: Any, bump_bps: float = 1.0) -> dict[str, Any]:
    shock_size = bump_bps / 10000.0
    base_pv = bound.valuation().price().base_pv
    rows = []
    for label, _boundary in KRD_BUCKETS:
        result = revalue_pack(
            bound,
            (
                Shock(
                    RiskFactorType.RATE,
                    shock_size,
                    ShockMode.ABSOLUTE,
                    tenor=label,
                    label=label,
                ),
            ),
        )
        pv01 = result["pnl"]
        rows.append(
            {
                "tenor": label,
                "bump_bps": bump_bps,
                "pv01": pv01,
                "key_rate_duration": -pv01 / (base_pv * shock_size) if base_pv and shock_size else 0.0,
            }
        )
    return stamp(
        bound,
        "KRD",
        {
            "base_pv": base_pv,
            "portfolio_pv01": sum(item["pv01"] for item in rows),
            "buckets": rows,
            "library": "FinancePy",
        },
        model="key_rate_duration",
    )


def pnl_explain(bound: Any, previous: Any) -> dict[str, Any]:
    snapshot = bound.snapshot
    prior = {item.security_code: item for item in previous.positions}
    current = {item.security_code: item for item in snapshot.positions}
    days = max((snapshot.as_of_date - previous.as_of_date).days, 1)
    rows = []
    totals = {
        "carry": 0.0,
        "rates": 0.0,
        "fx": 0.0,
        "credit": 0.0,
        "equity": 0.0,
        "volatility": 0.0,
        "position": 0.0,
        "residual": 0.0,
        "total": 0.0,
    }
    for code in sorted(set(prior) | set(current)):
        old = prior.get(code)
        new = current.get(code)
        old_pv = old.market_value_base if old else 0.0
        new_pv = new.market_value_base if new else 0.0
        total = new_pv - old_pv
        reference = new or old
        klass = str(getattr(reference, "asset_class", "") or "")
        carry = (old_pv * reference.coupon_rate * days / 365.0) if reference else 0.0
        rate_change = (new.ytm - old.ytm) if old and new else 0.0
        if abs(rate_change) > 1.0:
            rate_change /= 100.0
        rates = -old_pv * (old.duration if old else 0.0) * rate_change
        fx_change = (new.fx_rate / old.fx_rate - 1.0) if old and new and old.fx_rate else 0.0
        fx = (
            old_pv * fx_change
            if reference and reference.currency != snapshot.reporting_currency
            else 0.0
        )
        position_effect = (
            total if old is None or new is None else (new.market_value - old.market_value) * new.fx_rate
        )
        leftover = total - carry - rates - fx - position_effect
        credit = leftover if klass in {"BOND", "CD", "DEPOSIT", "CDS"} else 0.0
        equity = leftover if klass in {"EQUITY", "ETF", "FUTURE"} else 0.0
        volatility = leftover if klass in {"FX_OPTION", "SWAPTION", "OPTION"} else 0.0
        residual = leftover
        item = {
            "security_code": code,
            "asset_class": klass,
            "total_pnl": total,
            "carry": carry,
            "rates": rates,
            "fx": fx,
            "credit": credit,
            "equity": equity,
            "volatility": volatility,
            "position": position_effect,
            "residual": residual,
        }
        rows.append(item)
        for key in totals:
            totals[key] += item["total_pnl" if key == "total" else key]
    return stamp(
        bound,
        "PNL_EXPLAIN",
        {
            "start_date": previous.as_of_date.isoformat(),
            "end_date": snapshot.as_of_date.isoformat(),
            "totals": totals,
            "positions": sorted(rows, key=lambda item: abs(item["total_pnl"]), reverse=True),
        },
        model="snapshot_attribution",
    )


def var_backtest(bound: Any, confidence: float = 0.99, window: int = 60) -> dict[str, Any]:
    observations = nav_observations(bound.snapshot)
    returns = np.asarray([item[1] for item in observations], dtype=float)
    nav = float(bound.snapshot.net_asset or 0.0)
    if returns.size <= window:
        return stamp(
            bound,
            "VAR_BACKTEST",
            {"status": "INSUFFICIENT_DATA", "observations": int(returns.size), "points": []},
            model="riskfolio_nav",
        )
    adapter = bound.engine.riskfolio
    points = []
    exceptions = 0
    alpha = 1.0 - confidence
    for index in range(window, len(returns)):
        sample = returns[index - window : index]
        pack = adapter.historical_var_cvar(sample, confidence)
        var_return = float(pack["var"]) if pack.get("var") is not None else float(np.percentile(sample, alpha * 100.0))
        cvar_return = float(pack["cvar"]) if pack.get("cvar") is not None else var_return
        actual = float(returns[index])
        breached = actual < var_return
        exceptions += int(breached)
        points.append(
            {
                "date": observations[index][0].isoformat(),
                "actual_pnl": actual * nav,
                "var_limit": abs(var_return * nav),
                "cvar_limit": abs(cvar_return * nav),
                "actual_return_pct": actual * 100.0,
                "var_return_pct": abs(var_return) * 100.0,
                "exception": breached,
            }
        )
    count = len(points)
    ratio = exceptions / count if count else 0.0
    expected = alpha
    epsilon = 1e-12
    null_likelihood = (1 - expected) ** (count - exceptions) * expected ** exceptions
    alt_likelihood = (1 - ratio + epsilon) ** (count - exceptions) * (ratio + epsilon) ** exceptions
    kupiec_lr = max(-2.0 * math.log((null_likelihood + epsilon) / (alt_likelihood + epsilon)), 0.0)
    traffic_light = "GREEN" if exceptions <= max(4, math.ceil(count * alpha * 1.5)) else "YELLOW"
    if exceptions > max(9, math.ceil(count * alpha * 3.0)):
        traffic_light = "RED"
    return stamp(
        bound,
        "VAR_BACKTEST",
        {
            "status": "OK",
            "confidence": confidence,
            "window": window,
            "observations": count,
            "exceptions": exceptions,
            "exception_rate_pct": ratio * 100.0,
            "expected_exception_rate_pct": expected * 100.0,
            "kupiec_lr": kupiec_lr,
            "kupiec_reject_95": kupiec_lr > 3.841,
            "traffic_light": traffic_light,
            "latest_var_amount": points[-1]["var_limit"],
            "latest_cvar_amount": points[-1]["cvar_limit"],
            "points": points,
            "library": pack.get("engine"),
        },
        model="riskfolio_nav",
    )


def xva(
    bound: Any,
    counterparty_hazard: float = 0.02,
    own_hazard: float = 0.01,
    recovery_rate: float = 0.40,
    funding_spread: float = 0.01,
    initial_margin_pct: float = 0.05,
    mva_funding_spread: float = 0.008,
) -> dict[str, Any]:
    base_pv = bound.valuation().price().base_pv
    mapping = bound.engine.ore.map_snapshot(bound.snapshot)
    report = bound.engine.ore.xva(
        bound.snapshot,
        bound.engine.financepy,
        base_pv,
        counterparty_hazard=counterparty_hazard,
        own_hazard=own_hazard,
        recovery_rate=recovery_rate,
        funding_spread=funding_spread,
        initial_margin_pct=initial_margin_pct,
        mva_funding_spread=mva_funding_spread,
    )
    report["ore_mapping"] = mapping
    report["ore_app"] = False
    report["trades"] = [item["id"] for item in mapping.get("trades", [])]
    return stamp(bound, "XVA", report, model="ore_epe_ene")


def historical_backtest(
    bound: Any,
    market: Any | None = None,
    weight_mode: str = "CURRENT",
    custom_weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    from .backtest import run as run_backtest

    payload = run_backtest(bound, market=market, weight_mode=weight_mode, custom_weights=custom_weights)
    return stamp(bound, "HISTORICAL_BACKTEST", payload, model="historical_nav")
