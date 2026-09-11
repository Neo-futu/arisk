"""FinancePy vs ORE curve cross-check. Does not construct bond/swaption/CDS instruments."""
from __future__ import annotations

from typing import Any

from ..core.contracts import Shock, ShockMode, ValidationResult
from ..core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION

_TENORS = (1.0, 5.0)
_RATE = 0.03
_TOL = 1e-3


def compare_discount(bound: Any) -> list[dict[str, Any]]:
    as_of = bound.snapshot.as_of_date
    financepy = bound.engine.financepy
    ore = bound.engine.ore
    checks: list[dict[str, Any]] = []
    for years in _TENORS:
        fp_df = float(financepy.discount_factor(_RATE, years, as_of))
        ore_df = float(ore.discount_factor(_RATE, years, as_of))
        rel = abs(fp_df - ore_df) / abs(fp_df) if fp_df else abs(ore_df)
        checks.append(
            {
                "name": f"discount_factor_{int(years)}y",
                "passed": rel <= _TOL,
                "financepy": fp_df,
                "ore": ore_df,
                "relative_error": rel,
                "tolerance": _TOL,
            }
        )
    return checks


def compare_zero_shock(bound: Any) -> dict[str, Any]:
    priced = bound.valuation().price()
    kernel = bound.kernel().value()
    delta = abs(float(priced.base_pv) - float(kernel["base_pv"]))
    nav = abs(float(bound.snapshot.net_asset) or 1.0)
    return {
        "name": "zero_shock_pv_matches_kernel",
        "passed": delta / nav <= 1e-9 or delta <= 1e-6,
        "product_pv": priced.base_pv,
        "kernel_pv": kernel["base_pv"],
        "abs_diff": delta,
    }


def compare_rate_direction(bound: Any) -> dict[str, Any]:
    from ..core.contracts import RiskFactorType

    shock = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="cross_engine +1bp")
    product_pnl = bound.valuation().revalue((shock,)).pnl
    kernel_pnl = bound.kernel().value((shock,))["pnl"]
    same_sign = product_pnl * kernel_pnl >= 0.0 or abs(product_pnl) < 1e-9
    return {
        "name": "rate_up_sign_agrees",
        "passed": same_sign and product_pnl <= 1e-9,
        "product_pnl": product_pnl,
        "kernel_pnl": kernel_pnl,
    }


def run(bound: Any) -> ValidationResult:
    checks = [
        {
            "name": "ore_app_disabled",
            "passed": bound.engine.ore.map_snapshot(bound.snapshot).get("ore_app") is False,
        },
        *compare_discount(bound),
        compare_zero_shock(bound),
        compare_rate_direction(bound),
    ]
    passed = all(bool(item.get("passed")) for item in checks)
    return ValidationResult(
        status="PASS" if passed else "FAIL",
        checks=checks,
        context={
            "engine": RISKENGINE_NAME,
            "engine_version": RISKENGINE_VERSION,
            "model": "financepy_vs_ore_flat_curve",
            "curve": "FinancePy FlatDiscountCurve vs ORE FlatForward",
        },
    )
