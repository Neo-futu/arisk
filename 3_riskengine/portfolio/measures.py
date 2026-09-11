"""Portfolio Risk and Fund Risk packs. Riskfolio stays behind the adapter."""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from ..core.contracts import RiskFactorType, Shock, ShockMode, ViewMode
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ..market.snapshot import nav_returns
from .aggregate import aggregate
from .returns import implied_asset_returns, weights_from_positions

FACTOR_SHOCKS: tuple[Shock, ...] = (
    Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="rate_1bp"),
    Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="equity_1pct"),
    Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE, label="fx_1pct"),
    Shock(RiskFactorType.CREDIT_SPREAD, 0.0001, ShockMode.ABSOLUTE, label="cs_1bp"),
    Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE, label="vol_10pct"),
)


def _var_amount(pack: Mapping[str, Any], nav: float) -> dict[str, Any]:
    ret = pack.get("var")
    cvar = pack.get("cvar")
    return {
        "engine": pack.get("engine"),
        "status": pack.get("status"),
        "confidence": pack.get("confidence"),
        "observations": pack.get("observations"),
        "var_return": ret,
        "cvar_return": cvar,
        "var_amount": abs(float(ret) * nav) if ret is not None else None,
        "cvar_amount": abs(float(cvar) * nav) if cvar is not None else None,
    }


def _roll_class(contrib: Mapping[str, float], positions: list[dict[str, Any]]) -> dict[str, float]:
    by_code = {str(item["security_code"]): str(item["asset_class"]) for item in positions}
    buckets: dict[str, float] = {}
    for code, share in contrib.items():
        klass = by_code.get(code, "OTHER")
        buckets[klass] = buckets.get(klass, 0.0) + float(share)
    total = sum(buckets.values()) or 1.0
    return {key: value / total for key, value in buckets.items()}


def factor_pnl_contribution(bound: Any, view: ViewMode | str = ViewMode.LOOK_THROUGH) -> dict[str, Any]:
    """Cross-product RC from unified revaluation of standard factor shocks."""

    by_code: dict[str, float] = {}
    by_class: dict[str, float] = {}
    by_factor: list[dict[str, Any]] = []
    for shock in FACTOR_SHOCKS:
        priced = bound.valuation().revalue((shock,), view=view)
        total = float(priced.pnl) or 0.0
        denom = abs(total) if abs(total) > 1e-12 else 1.0
        rows = []
        for item in priced.trade_values:
            share = float(item["pnl"]) / denom
            code = str(item["security_code"])
            klass = str(item["asset_class"])
            by_code[code] = by_code.get(code, 0.0) + abs(float(item["pnl"]))
            by_class[klass] = by_class.get(klass, 0.0) + abs(float(item["pnl"]))
            rows.append({"security_code": code, "asset_class": klass, "pnl": item["pnl"], "share": share})
        by_factor.append(
            {
                "factor": shock.label or str(getattr(shock.factor_type, "value", shock.factor_type)),
                "pnl": total,
                "rows": rows,
            }
        )
    code_total = sum(by_code.values()) or 1.0
    class_total = sum(by_class.values()) or 1.0
    return {
        "by_security": {key: value / code_total for key, value in by_code.items()},
        "by_asset_class": {key: value / class_total for key, value in by_class.items()},
        "factors": by_factor,
    }


def portfolio_risk(
    bound: Any,
    *,
    confidence: float = 0.99,
    returns: Any | None = None,
) -> dict[str, Any]:
    """Look-through book: product PV + exposure + VaR/CVaR + RC + optional optimize inputs."""

    book = aggregate(bound, view=ViewMode.LOOK_THROUGH)
    snapshot = bound.snapshot
    nav = float(book["nav"] or 0.0)
    adapter = bound.engine.riskfolio
    hist = adapter.historical_var_cvar(nav_returns(snapshot), confidence)
    weights = weights_from_positions(book["positions"])
    panel = returns if returns is not None else implied_asset_returns(snapshot, book["positions"])
    statistical = adapter.risk_contribution(weights, panel, confidence=confidence) if not panel.empty else {}
    factor = factor_pnl_contribution(bound, ViewMode.LOOK_THROUGH)
    return {
        "scope": "PORTFOLIO",
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        **book,
        "var_cvar": _var_amount(hist, nav),
        "risk_contribution": {
            "statistical": statistical,
            "by_asset_class": _roll_class(statistical, book["positions"]) if statistical else factor["by_asset_class"],
            "factor_pnl": factor,
        },
        "returns_columns": list(panel.columns) if not panel.empty else [],
        "riskfolio_available": adapter.available,
    }


def fund_risk(bound: Any, *, confidence: float = 0.99) -> dict[str, Any]:
    """Share-class / PRODUCT view: NAV VaR/CVaR on fsi.balance_portfolio_nav."""

    book = aggregate(bound, view=ViewMode.PRODUCT)
    snapshot = bound.snapshot
    nav = float(book["nav"] or 0.0)
    series = nav_returns(snapshot)
    hist = bound.engine.riskfolio.historical_var_cvar(series, confidence)
    vol = None
    drawdown = None
    if series.size >= 2:
        vol = float(np.std(series, ddof=1) * math.sqrt(252))
        wealth = np.cumprod(1.0 + series)
        peaks = np.maximum.accumulate(wealth)
        drawdown = float(np.min(wealth / peaks - 1.0))
    return {
        "scope": "FUND",
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "fund_id": book["fund_id"],
        "as_of": book["as_of"],
        "reporting_currency": book["reporting_currency"],
        "view": book["view"],
        "nav": nav,
        "base_pv": book["base_pv"],
        "product_count": book["position_count"],
        "products": book["positions"],
        "by_asset_class": book["by_asset_class"],
        "var_cvar": _var_amount(hist, nav),
        "volatility_ann": vol,
        "max_drawdown": drawdown,
        "riskfolio_available": bound.engine.riskfolio.available,
    }


def optimize_book(
    bound: Any,
    method: str,
    *,
    returns: Any | None = None,
    constraints: Mapping[str, Any] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    confidence: float = 0.95,
) -> dict[str, Any]:
    book = aggregate(bound, view=ViewMode.LOOK_THROUGH)
    panel = returns if returns is not None else implied_asset_returns(bound.snapshot, book["positions"])
    current = weights_from_positions(book["positions"])
    if panel.empty:
        n = max(len(current), 1)
        weights = {key: 1.0 / n for key in current} if current else {}
        return {
            "method": method,
            "weights": weights,
            "risk_contribution": {key: 1.0 / n for key in weights} if weights else {},
            "engine": "riskengine_fallback",
            "available": bound.engine.riskfolio.available,
            "is_trade_instruction": False,
            "status": "INSUFFICIENT_DATA",
            "current_weights": current,
        }
    result = bound.engine.riskfolio.optimize(
        panel,
        method,
        constraints=constraints,
        current_weights=current,
        views=views,
        risk_budgets=risk_budgets,
        confidence=confidence,
    )
    result["current_weights"] = current
    result["scope"] = "PORTFOLIO"
    return result
