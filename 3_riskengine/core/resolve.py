"""Vendor-neutral engine routing. Business code must not pick FinancePy / ORE / Riskfolio."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import AnalyticKind, Product, ProductKind, ValuationContext


@dataclass(frozen=True)
class EngineRef:
    adapter: str
    model: str
    fallback: str | None = None


_PORTFOLIO_ANALYTICS = {
    AnalyticKind.VAR.value: EngineRef("riskfolio", "historical_var", "riskengine_numpy"),
    AnalyticKind.CVAR.value: EngineRef("riskfolio", "historical_cvar", "riskengine_numpy"),
    AnalyticKind.ES.value: EngineRef("riskfolio", "historical_es", "riskengine_numpy"),
    AnalyticKind.OPTIMIZE.value: EngineRef("riskfolio", "portfolio_optimize", "riskengine_fallback"),
    AnalyticKind.STRESS.value: EngineRef("riskengine", "product_revalue", "financepy"),
    AnalyticKind.SCENARIO.value: EngineRef("riskengine", "product_revalue", "financepy"),
    AnalyticKind.REVERSE_STRESS.value: EngineRef("riskengine", "product_revalue", "financepy"),
    AnalyticKind.TAIL_RISK.value: EngineRef("riskfolio", "historical_var", "riskengine_numpy"),
    AnalyticKind.KRD.value: EngineRef("financepy", "key_rate_duration", "riskengine"),
    AnalyticKind.PNL_EXPLAIN.value: EngineRef("riskengine", "pnl_explain", None),
    AnalyticKind.HISTORICAL_BACKTEST.value: EngineRef("riskengine", "historical_backtest", None),
    AnalyticKind.VAR_BACKTEST.value: EngineRef("riskfolio", "var_backtest", "riskengine_numpy"),
    AnalyticKind.LIQUIDITY.value: EngineRef("riskengine", "product_liquidity_buckets", None),
}

_PRODUCT_PRICE: dict[str, EngineRef] = {
    ProductKind.EQUITY.value: EngineRef("financepy", "equity_spot", "market_value"),
    ProductKind.BOND.value: EngineRef("financepy", "bond_discount_curve", "duration_proxy"),
    ProductKind.DEPOSIT.value: EngineRef("financepy", "ibor_deposit", "accrual"),
    ProductKind.CD.value: EngineRef("financepy", "bond_zero_or_deposit", "accrual"),
    ProductKind.REPO.value: EngineRef("financepy", "repo_carry", None),
    ProductKind.CASH.value: EngineRef("riskengine", "cash_balance", None),
    ProductKind.MMF.value: EngineRef("riskengine", "mmf_nav_yield", "financepy"),
    ProductKind.FUND.value: EngineRef("riskengine", "fund_nav", "market_value"),
    ProductKind.ETF.value: EngineRef("financepy", "equity_spot", "market_value"),
    ProductKind.FX.value: EngineRef("ore", "fx_spot", "market_value"),
    ProductKind.FX_FORWARD.value: EngineRef("ore", "fx_forward", "financepy"),
    ProductKind.FX_OPTION.value: EngineRef("ore", "fx_option", "financepy"),
    ProductKind.FUTURE.value: EngineRef("ore", "future", "financepy"),
    ProductKind.OPTION.value: EngineRef("ore", "equity_option", "financepy"),
    ProductKind.IRS.value: EngineRef("ore", "irs", None),
    ProductKind.SWAP.value: EngineRef("ore", "swap", None),
    ProductKind.SWAPTION.value: EngineRef("ore", "swaption", None),
    ProductKind.CDS.value: EngineRef("ore", "cds", None),
    ProductKind.STRUCTURED.value: EngineRef("ore", "scripted_or_otc", None),
}

_ANALYTIC_OVERRIDE: dict[str, EngineRef] = {
    AnalyticKind.XVA.value: EngineRef("ore", "xva_epe_ene", "riskengine_deterministic"),
    AnalyticKind.EXPOSURE.value: EngineRef("riskengine", "position_aggregation", None),
    AnalyticKind.GREEKS.value: EngineRef("financepy", "bump_and_revalue", "ore"),
    AnalyticKind.CASHFLOW.value: EngineRef("financepy", "product_cashflows", "ore"),
}


def _kind(product: Product | ProductKind | str) -> str:
    if isinstance(product, Product):
        return ProductKind(product.kind).value
    if isinstance(product, ProductKind):
        return product.value
    return str(product).strip().upper()


def _analytic(risk_type: AnalyticKind | str) -> str:
    if isinstance(risk_type, AnalyticKind):
        return risk_type.value
    return str(risk_type).strip().upper()


def resolve(
    product: Product | ProductKind | str,
    risk_type: AnalyticKind | str,
    valuation_context: ValuationContext | None = None,
) -> EngineRef:
    """Map a product and analytic onto an adapter. No vendor imports."""

    del valuation_context
    analytic = _analytic(risk_type)
    if analytic == AnalyticKind.SENSITIVITY.value:
        analytic = AnalyticKind.GREEKS.value
    if analytic in _PORTFOLIO_ANALYTICS:
        return _PORTFOLIO_ANALYTICS[analytic]
    if analytic in _ANALYTIC_OVERRIDE and analytic not in {
        AnalyticKind.GREEKS.value,
        AnalyticKind.CASHFLOW.value,
    }:
        return _ANALYTIC_OVERRIDE[analytic]
    kind = _kind(product)
    if analytic == AnalyticKind.GREEKS.value and kind in {
        ProductKind.IRS.value,
        ProductKind.SWAP.value,
        ProductKind.CDS.value,
        ProductKind.STRUCTURED.value,
        ProductKind.FX_OPTION.value,
        ProductKind.FX_FORWARD.value,
        ProductKind.FX.value,
        ProductKind.FUTURE.value,
        ProductKind.OPTION.value,
        ProductKind.SWAPTION.value,
    }:
        return EngineRef("ore", "greeks", "financepy")
    if kind in _PRODUCT_PRICE:
        if analytic in {AnalyticKind.PRICE.value, AnalyticKind.GREEKS.value, AnalyticKind.CASHFLOW.value}:
            return _PRODUCT_PRICE[kind]
        return _PRODUCT_PRICE[kind]
    raise ValueError(f"Unsupported product/analytic routing: {kind!r} / {analytic!r}")
