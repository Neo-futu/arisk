"""Investment-risk KPI calculations on an existing ARISK portfolio snapshot.

Inputs are ``fsi.balance_*`` / ``fsi.mktdata_*`` snapshots already loaded by
``risk_testing.loader``. This module does not open a second master-data store.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np

from ..core.engine import RiskEngine
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..adapters.riskfolio import RiskfolioAdapter
from ..instruments.classify import EQUITY_LIKE, FIXED_INCOME, issuer_name

KPI_IDS: tuple[str, ...] = (
    "VaR",
    "CVaR",
    "ES",
    "Volatility",
    "Drawdown",
    "Beta",
    "Tracking Error",
    "Risk Contribution",
    "Gross Exposure",
    "Net Exposure",
    "Factor Exposure",
    "Duration",
    "DV01",
    "KRD",
    "CS01",
    "Liquidity",
    "Concentration",
    "Counterparty Exposure",
    "PFE",
    "EPE",
    "Leverage",
)

LIQUID = {"CASH", "DEPOSIT"}


def _report(
    kpi: str,
    *,
    inputs: dict[str, Any],
    calculation: str,
    engine: str,
    formula: str,
    result: Any,
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kpi": kpi,
        "input": inputs,
        "calculation": calculation,
        "engine": engine,
        "formula": formula,
        "result": result,
        "data_quality": data_quality,
        "engine_version": RISKENGINE_VERSION,
        "platform_engine": RISKENGINE_NAME,
    }


def _kernel(snapshot: Any) -> Any:
    return RiskEngine().bind(snapshot).kernel()


def _nav_returns(snapshot: Any) -> np.ndarray:
    return np.asarray([item[1] for item in snapshot.nav_returns], dtype=float)


def _quality(snapshot: Any, **extra: Any) -> dict[str, Any]:
    payload = dict(getattr(snapshot, "data_quality", {}) or {})
    payload.update(extra)
    payload.setdefault("source_tables", ["fsi.balance_*", "fsi.mktdata_*"])
    payload.setdefault("position_count", len(snapshot.positions))
    payload.setdefault("nav", snapshot.net_asset)
    return payload


def _var_cvar(returns: np.ndarray, confidence: float) -> tuple[float | None, float | None, str]:
    adapter = RiskfolioAdapter()
    pack = adapter.historical_var_cvar(returns, confidence)
    if pack["status"] != "OK" or pack["var"] is None:
        return None, None, pack.get("engine") or "riskengine_numpy"
    return float(pack["var"]), float(pack["cvar"]), str(pack["engine"])


def kpi_var(snapshot: Any, confidence: float = 0.99) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    var_r, _, engine = _var_cvar(returns, confidence)
    amount = abs(var_r * snapshot.net_asset) if var_r is not None else None
    return _report(
        "VaR",
        inputs={"confidence": confidence, "observations": int(returns.size), "nav": snapshot.net_asset},
        calculation="historical_percentile_of_nav_returns",
        engine=engine,
        formula="VaR_α = -Q_α(R) × NAV  (historical, left-tail quantile)",
        result={"return": var_r, "amount": amount, "confidence": confidence},
        data_quality=_quality(snapshot, sample_size=int(returns.size), sufficient=returns.size >= 20),
    )


def kpi_cvar(snapshot: Any, confidence: float = 0.99) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    var_r, cvar_r, engine = _var_cvar(returns, confidence)
    amount = abs(cvar_r * snapshot.net_asset) if cvar_r is not None else None
    return _report(
        "CVaR",
        inputs={"confidence": confidence, "observations": int(returns.size), "nav": snapshot.net_asset},
        calculation="mean_of_returns_at_or_below_historical_var",
        engine=engine,
        formula="CVaR_α = -E[R | R ≤ Q_α(R)] × NAV",
        result={"return": cvar_r, "amount": amount, "var_return": var_r, "confidence": confidence},
        data_quality=_quality(snapshot, sample_size=int(returns.size), sufficient=returns.size >= 20),
    )


def kpi_es(snapshot: Any, confidence: float = 0.99) -> dict[str, Any]:
    """Expected Shortfall. Historical ES coincides with historical CVaR."""

    cvar = kpi_cvar(snapshot, confidence)
    return _report(
        "ES",
        inputs=cvar["input"],
        calculation="historical_expected_shortfall_identical_to_cvar",
        engine=cvar["engine"],
        formula="ES_α ≡ CVaR_α under the historical (empirical) measure",
        result=cvar["result"],
        data_quality=cvar["data_quality"],
    )


def kpi_volatility(snapshot: Any) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    vol = float(np.std(returns, ddof=1) * math.sqrt(252)) if returns.size >= 2 else None
    return _report(
        "Volatility",
        inputs={"observations": int(returns.size), "ann_factor": 252},
        calculation="sample_stdev_times_sqrt_252",
        engine="riskengine_numpy",
        formula="σ_ann = stdev(R) × √252",
        result={"annualized": vol, "annualized_pct": vol * 100.0 if vol is not None else None},
        data_quality=_quality(snapshot, sample_size=int(returns.size), sufficient=returns.size >= 2),
    )


def kpi_drawdown(snapshot: Any) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    if returns.size == 0:
        dd = None
        wealth = np.array([])
    else:
        wealth = np.cumprod(1.0 + returns)
        peaks = np.maximum.accumulate(wealth)
        dd = float(np.min(wealth / peaks - 1.0))
    return _report(
        "Drawdown",
        inputs={"observations": int(returns.size)},
        calculation="peak_to_trough_on_nav_wealth_index",
        engine="riskengine_numpy",
        formula="MDD = min_t (W_t / max_{s≤t} W_s - 1)",
        result={"max_drawdown": dd, "max_drawdown_pct": dd * 100.0 if dd is not None else None},
        data_quality=_quality(snapshot, sample_size=int(returns.size), sufficient=returns.size >= 2),
    )


def kpi_beta(snapshot: Any, benchmark_returns: Iterable[float] | None = None) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    bench = np.asarray(list(benchmark_returns or []), dtype=float)
    n = min(returns.size, bench.size)
    value = None
    if n >= 3:
        a = returns[-n:]
        b = bench[-n:]
        var_b = float(np.var(b, ddof=1))
        if var_b > 0:
            value = float(np.cov(a, b, ddof=1)[0, 1] / var_b)
    return _report(
        "Beta",
        inputs={"asset_obs": int(returns.size), "benchmark_obs": int(bench.size), "paired": n},
        calculation="sample_covariance_over_benchmark_variance",
        engine="riskengine_numpy",
        formula="β = Cov(R_p, R_b) / Var(R_b)",
        result={"beta": value, "paired_observations": n},
        data_quality=_quality(snapshot, sufficient=n >= 3, paired_observations=n),
    )


def kpi_tracking_error(snapshot: Any, benchmark_returns: Iterable[float] | None = None) -> dict[str, Any]:
    returns = _nav_returns(snapshot)
    bench = np.asarray(list(benchmark_returns or []), dtype=float)
    n = min(returns.size, bench.size)
    te = None
    if n >= 3:
        te = float(np.std(returns[-n:] - bench[-n:], ddof=1) * math.sqrt(252))
    return _report(
        "Tracking Error",
        inputs={"paired": n, "ann_factor": 252},
        calculation="annualized_stdev_of_active_returns",
        engine="riskengine_numpy",
        formula="TE = stdev(R_p - R_b) × √252",
        result={"annualized": te, "annualized_pct": te * 100.0 if te is not None else None},
        data_quality=_quality(snapshot, sufficient=n >= 3, paired_observations=n),
    )


def kpi_risk_contribution(snapshot: Any) -> dict[str, Any]:
    from ..core.contracts import RiskFactorType, Shock, ShockMode

    shock = Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="equity +1%")
    valued = _kernel(snapshot).value((shock,))
    total = float(valued["pnl"]) or 1.0
    rows = [
        {
            "security_code": item["security_code"],
            "pnl": item["pnl"],
            "contribution_pct": item["pnl"] / total * 100.0,
        }
        for item in valued["trade_values"]
    ]
    return _report(
        "Risk Contribution",
        inputs={"shock": "EQUITY +1% relative", "nav": snapshot.net_asset},
        calculation="trade_pnl_share_under_unified_revaluation_shock",
        engine="financepy_riskengine",
        formula="RC_i = PnL_i(shock) / Σ_j PnL_j(shock)",
        result={"rows": rows, "shock_pnl": valued["pnl"]},
        data_quality=_quality(snapshot, sufficient=len(rows) > 0),
    )


def kpi_gross_exposure(snapshot: Any) -> dict[str, Any]:
    gross = sum(abs(p.market_value_base) for p in snapshot.positions)
    ratio = gross / snapshot.net_asset if snapshot.net_asset else None
    return _report(
        "Gross Exposure",
        inputs={"nav": snapshot.net_asset, "positions": len(snapshot.positions)},
        calculation="sum_abs_market_value_base_over_nav",
        engine=RISKENGINE_NAME,
        formula="Gross = Σ |MV_i| / NAV",
        result={"amount": gross, "ratio": ratio, "pct_nav": ratio * 100.0 if ratio is not None else None},
        data_quality=_quality(snapshot, sufficient=snapshot.net_asset > 0),
    )


def kpi_net_exposure(snapshot: Any) -> dict[str, Any]:
    net = sum(p.market_value_base for p in snapshot.positions)
    ratio = net / snapshot.net_asset if snapshot.net_asset else None
    return _report(
        "Net Exposure",
        inputs={"nav": snapshot.net_asset},
        calculation="sum_signed_market_value_base_over_nav",
        engine=RISKENGINE_NAME,
        formula="Net = Σ MV_i / NAV",
        result={"amount": net, "ratio": ratio, "pct_nav": ratio * 100.0 if ratio is not None else None},
        data_quality=_quality(snapshot, sufficient=snapshot.net_asset > 0),
    )


def kpi_factor_exposure(snapshot: Any) -> dict[str, Any]:
    buckets = defaultdict(float)
    for position in snapshot.positions:
        if position.asset_class in FIXED_INCOME:
            factor = "RATE_CREDIT"
        elif position.asset_class in EQUITY_LIKE:
            factor = "EQUITY"
        elif position.asset_class == "CASH":
            factor = "CASH"
        else:
            factor = position.asset_class or "OTHER"
        if position.currency != snapshot.reporting_currency:
            buckets["FX"] += abs(position.market_value_base)
        buckets[factor] += abs(position.market_value_base)
    nav = snapshot.net_asset or 1.0
    rows = {key: {"amount": value, "pct_nav": value / nav * 100.0} for key, value in buckets.items()}
    return _report(
        "Factor Exposure",
        inputs={"reporting_currency": snapshot.reporting_currency, "nav": snapshot.net_asset},
        calculation="absolute_mv_grouped_by_rate_equity_fx_cash",
        engine=RISKENGINE_NAME,
        formula="FE_f = Σ_{i∈f} |MV_i| / NAV",
        result=rows,
        data_quality=_quality(snapshot, factors=sorted(rows)),
    )


def kpi_duration(snapshot: Any) -> dict[str, Any]:
    fi = [p for p in snapshot.positions if p.asset_class in FIXED_INCOME]
    mv = sum(p.market_value_base for p in fi)
    weighted = sum(p.market_value_base * p.duration for p in fi) / mv if mv else None
    return _report(
        "Duration",
        inputs={"fixed_income_mv": mv, "count": len(fi)},
        calculation="market_value_weighted_modified_duration",
        engine=RISKENGINE_NAME,
        formula="D = Σ (MV_i × D_i) / Σ MV_i   for bonds/CD/deposits",
        result={"weighted_years": weighted, "fixed_income_mv": mv},
        data_quality=_quality(snapshot, fixed_income_count=len(fi), sufficient=bool(fi)),
    )


def kpi_dv01(snapshot: Any) -> dict[str, Any]:
    from ..core.contracts import RiskFactorType, Shock, ShockMode

    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="rate +1bp")
    valued = _kernel(snapshot).value((shock,))
    proxy = sum(
        p.market_value_base * p.duration * 0.0001
        for p in snapshot.positions
        if p.asset_class in FIXED_INCOME
    )
    return _report(
        "DV01",
        inputs={"bump_bps": 1.0, "nav": snapshot.net_asset},
        calculation="financepy_1bp_parallel_revaluation_and_duration_proxy",
        engine="financepy_riskengine",
        formula="DV01 ≈ PV(r+1bp) - PV(r) ; proxy = Σ MV_i × D_i × 0.0001",
        result={"reval_pnl": valued["pnl"], "duration_proxy": proxy},
        data_quality=_quality(snapshot, financepy=True),
    )


def kpi_krd(snapshot: Any) -> dict[str, Any]:
    report = _kernel(snapshot).krd(1.0)
    return _report(
        "KRD",
        inputs={"bump_bps": 1.0, "buckets": [item["tenor"] for item in report.get("buckets", [])]},
        calculation="key_rate_isolated_financepy_revaluation",
        engine="financepy_riskengine",
        formula="KRD_k = -ΔPV_k / (PV × 0.0001)  with tenor-isolated +1bp",
        result={"portfolio_pv01": report.get("portfolio_pv01"), "buckets": report.get("buckets")},
        data_quality=_quality(snapshot, analytic=report.get("analytic")),
    )


def kpi_cs01(snapshot: Any) -> dict[str, Any]:
    proxy = sum(
        p.market_value_base * p.duration * 0.8 * 0.0001
        for p in snapshot.positions
        if p.asset_class in FIXED_INCOME
    )
    from ..core.contracts import RiskFactorType, Shock, ShockMode

    shock = Shock(RiskFactorType.CREDIT_SPREAD, 0.0001, ShockMode.ABSOLUTE)
    valued = _kernel(snapshot).value((shock,))
    return _report(
        "CS01",
        inputs={"bump_bps": 1.0, "spread_duration_factor": 0.8},
        calculation="financepy_credit_spread_1bp_reval_and_80pct_duration_proxy",
        engine="financepy_riskengine",
        formula="CS01 ≈ PV(s+1bp)-PV(s) ; proxy = Σ MV_i × 0.8 D_i × 0.0001",
        result={"reval_pnl": valued["pnl"], "duration_proxy": proxy},
        data_quality=_quality(snapshot, assumption="spread duration proxied at 80% of duration when missing"),
    )


def kpi_liquidity(snapshot: Any) -> dict[str, Any]:
    liquid = sum(
        p.market_value_base
        for p in snapshot.positions
        if p.asset_class in LIQUID or (p.asset_class in FIXED_INCOME and p.duration <= 0.25)
    )
    ratio = liquid / snapshot.net_asset if snapshot.net_asset else None
    return _report(
        "Liquidity",
        inputs={"nav": snapshot.net_asset, "liquid_classes": sorted(LIQUID), "short_duration_years": 0.25},
        calculation="cash_deposit_and_short_duration_mv_over_nav",
        engine=RISKENGINE_NAME,
        formula="L = (Σ_{cash,deposit} MV + Σ_{D≤0.25y} MV) / NAV",
        result={"amount": liquid, "pct_nav": ratio * 100.0 if ratio is not None else None},
        data_quality=_quality(snapshot, sufficient=snapshot.net_asset > 0),
    )


def kpi_concentration(snapshot: Any) -> dict[str, Any]:
    nav = snapshot.net_asset or 1.0
    weights = [abs(p.market_value_base) / nav for p in snapshot.positions]
    hhi = sum(w * w for w in weights) * 10000
    top = sorted(snapshot.positions, key=lambda p: abs(p.market_value_base), reverse=True)[:5]
    return _report(
        "Concentration",
        inputs={"nav": snapshot.net_asset, "names": len(snapshot.positions)},
        calculation="herfindahl_hirschman_on_abs_mv_weights",
        engine=RISKENGINE_NAME,
        formula="HHI = 10,000 × Σ w_i² , w_i = |MV_i| / NAV",
        result={
            "hhi": hhi,
            "top5": [
                {"security_code": p.security_code, "pct_nav": abs(p.market_value_base) / nav * 100.0}
                for p in top
            ],
        },
        data_quality=_quality(snapshot, sufficient=bool(snapshot.positions)),
    )


def kpi_counterparty_exposure(snapshot: Any) -> dict[str, Any]:
    buckets: dict[str, float] = defaultdict(float)
    for position in snapshot.positions:
        name = issuer_name(position)
        buckets[name] += abs(position.market_value_base)
    nav = snapshot.net_asset or 1.0
    rows = [
        {"counterparty": name, "amount": amount, "pct_nav": amount / nav * 100.0}
        for name, amount in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    ]
    return _report(
        "Counterparty Exposure",
        inputs={"nav": snapshot.net_asset},
        calculation="absolute_mv_grouped_by_issuer_or_security_name",
        engine=RISKENGINE_NAME,
        formula="CE_c = Σ_{i∈c} |MV_i| / NAV",
        result={"rows": rows[:20], "counterparty_count": len(rows)},
        data_quality=_quality(snapshot, grouping="metadata.issuer_name else security_name"),
    )


def kpi_pfe(snapshot: Any) -> dict[str, Any]:
    profile = _xva_profile(snapshot)
    epe_values = [item["epe"] for item in profile]
    pfe = max(epe_values) if epe_values else None
    return _report(
        "PFE",
        inputs={"xva_steps": len(profile), "nav": snapshot.net_asset},
        calculation="peak_epe_on_deterministic_exposure_profile",
        engine="financepy_riskengine",
        formula="PFE ≈ max_t EPE(t)  (deterministic profile; simulated PFE is an ORE extension)",
        result={"amount": pfe, "steps": len(profile)},
        data_quality=_quality(snapshot, ore_simulated=False, sufficient=bool(profile)),
    )


def kpi_epe(snapshot: Any) -> dict[str, Any]:
    profile = _xva_profile(snapshot)
    epe_values = [item["epe"] for item in profile]
    epe = float(np.mean(epe_values)) if epe_values else None
    return _report(
        "EPE",
        inputs={"xva_steps": len(profile)},
        calculation="mean_epe_on_deterministic_exposure_profile",
        engine="financepy_riskengine",
        formula="EPE = mean_t EPE(t) from discounted exposure integration",
        result={"amount": epe, "steps": len(profile)},
        data_quality=_quality(snapshot, ore_simulated=False, sufficient=bool(profile)),
    )


def kpi_leverage(snapshot: Any) -> dict[str, Any]:
    gross = kpi_gross_exposure(snapshot)
    ratio = gross["result"]["ratio"]
    return _report(
        "Leverage",
        inputs={"nav": snapshot.net_asset},
        calculation="gross_exposure_as_economic_leverage",
        engine=RISKENGINE_NAME,
        formula="Leverage = Σ |MV_i| / NAV",
        result={"ratio": ratio, "pct": ratio * 100.0 if ratio is not None else None},
        data_quality=_quality(snapshot, sufficient=snapshot.net_asset > 0),
    )


def _xva_profile(snapshot: Any) -> list[dict[str, Any]]:
    report = _kernel(snapshot).xva(0.02, 0.01, 0.40, 0.01, 0.05, 0.008)
    return list(report.get("exposure_profile") or [])


KPI_FUNCS: dict[str, Any] = {
    "VaR": kpi_var,
    "CVaR": kpi_cvar,
    "ES": kpi_es,
    "Volatility": kpi_volatility,
    "Drawdown": kpi_drawdown,
    "Beta": kpi_beta,
    "Tracking Error": kpi_tracking_error,
    "Risk Contribution": kpi_risk_contribution,
    "Gross Exposure": kpi_gross_exposure,
    "Net Exposure": kpi_net_exposure,
    "Factor Exposure": kpi_factor_exposure,
    "Duration": kpi_duration,
    "DV01": kpi_dv01,
    "KRD": kpi_krd,
    "CS01": kpi_cs01,
    "Liquidity": kpi_liquidity,
    "Concentration": kpi_concentration,
    "Counterparty Exposure": kpi_counterparty_exposure,
    "PFE": kpi_pfe,
    "EPE": kpi_epe,
    "Leverage": kpi_leverage,
}


def compute_selected(
    snapshot: Any,
    kpi_ids: Iterable[str],
    *,
    confidence: float = 0.99,
    benchmark_returns: Iterable[float] | None = None,
) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for kpi_id in kpi_ids:
        func = KPI_FUNCS[kpi_id]
        kwargs: dict[str, Any] = {}
        names = func.__code__.co_varnames
        if "confidence" in names:
            kwargs["confidence"] = confidence
        if "benchmark_returns" in names:
            kwargs["benchmark_returns"] = benchmark_returns
        reports[kpi_id] = func(snapshot, **kwargs)
    return reports


def compute_kpi_pack(
    snapshot: Any,
    *,
    confidence: float = 0.99,
    benchmark_returns: Iterable[float] | None = None,
) -> dict[str, Any]:
    kpis = compute_selected(
        snapshot,
        KPI_IDS,
        confidence=confidence,
        benchmark_returns=benchmark_returns,
    )
    return {
        "fund_id": snapshot.fund_id,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "reporting_currency": snapshot.reporting_currency,
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "kpis": kpis,
        "data_quality": _quality(snapshot),
    }
