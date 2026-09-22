"""ORE adapter. Vendor import is isolated here.

Prefers the installed ORE-SWIG package (``site-packages/ORE``). The workspace
``ORE/`` tree is C++ reference source and must not count as bindings.
"""
from __future__ import annotations

import importlib.util
import math
import site
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

from ...instruments.classify import coupon_rate, is_fixed_income, years_to_maturity
from ..vendor import VendorProbe, probe_module

_ORE_SWIG_MARKERS = (
    "OREApp",
    "InputParameters",
    "XvaCalculator",
    "XVACalculator",
    "AnalyticsManager",
    "ExposureCalculator",
    "ScenarioGenerator",
)
ORE_CORE_CALLS = [
    "ORE.Date",
    "ORE.Settings",
    "ORE.FlatForward",
    "ORE.FlatHazardRate",
    "ORE.FxForward",
    "ORE.DiscountingFxForwardEngine",
    "ORE.MakeVanillaSwap",
    "ORE.DiscountingSwapEngine",
    "ORE.blackFormula",
    "ORE.VanillaOption",
    "ORE.AnalyticEuropeanEngine",
    "ORE.BinomialVanillaEngine",
]
QUANTLIB_CORE_CALLS = [
    "QuantLib.Date",
    "QuantLib.Settings",
    "QuantLib.FlatForward",
    "QuantLib.FlatHazardRate",
    "QuantLib.DiscountingBondEngine",
    "QuantLib.FixedRateBond",
]


def _is_ore_swig(module: Any) -> bool:
    """True only for compiled ORE-SWIG, not the local C++ source namespace."""

    if module is None:
        return False
    names = {item for item in dir(module) if not item.startswith("_")}
    if not names:
        return False
    return bool(names.intersection(_ORE_SWIG_MARKERS))


def _load_ore_from_site_packages() -> tuple[VendorProbe, ModuleType | None]:
    """Bypass a shadowed workspace ``ORE/`` namespace and load site-packages ORE."""

    candidates: list[Path] = []
    for root in list(site.getsitepackages()) + [site.getusersitepackages()]:
        if not root:
            continue
        init = Path(root) / "ORE" / "__init__.py"
        if init.is_file():
            candidates.append(init)
    for init in candidates:
        try:
            spec = importlib.util.spec_from_file_location("_arisk_ore_swig", init)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            # Keep SWIG extension discovery working relative to the package.
            sys.modules.setdefault("_arisk_ore_swig", module)
            spec.loader.exec_module(module)
            if _is_ore_swig(module):
                version = getattr(module, "__version__", None)
                return (
                    VendorProbe(
                        "ORE",
                        True,
                        str(version) if version is not None else None,
                        str(init),
                        None,
                    ),
                    module,
                )
        except Exception as exc:  # noqa: BLE001 — probe must never raise
            last_error = f"{type(exc).__name__}: {exc}"
            return VendorProbe("ORE", False, None, str(init), last_error), None
    return (
        VendorProbe(
            "ORE",
            False,
            None,
            None,
            "ORE-SWIG not found under site-packages",
        ),
        None,
    )


def _probe_ore_swig() -> tuple[VendorProbe, ModuleType | None, str | None]:
    probe, module = probe_module("ORE")
    if probe.available and _is_ore_swig(module):
        return probe, module, None
    if probe.available and not _is_ore_swig(module):
        # Workspace ORE/ is often a namespace package on sys.path[0].
        site_probe, site_mod = _load_ore_from_site_packages()
        if site_probe.available and site_mod is not None:
            return site_probe, site_mod, None
        return (
            site_probe,
            None,
            "workspace ORE/ is reference source, not compiled ORE-SWIG bindings",
        )
    site_probe, site_mod = _load_ore_from_site_packages()
    if site_probe.available and site_mod is not None:
        return site_probe, site_mod, None
    return site_probe, None, site_probe.error or probe.error or "ORE-SWIG is not installed"


@contextmanager
def _ql_evaluation(ql: Any, as_of: date) -> Iterator[Any]:
    settings = ql.Settings.instance()
    previous = ql.Date(settings.evaluationDate.serialNumber())
    as_of_ql = ql.Date(as_of.day, as_of.month, as_of.year)
    settings.evaluationDate = as_of_ql
    try:
        yield as_of_ql
    finally:
        settings.evaluationDate = previous


class OREAdapter:
    """Complex derivatives / XVA / scenario adapter.

    Maps ARISK platform positions onto ORE-style trade descriptors.
    Pricing order: ORE-SWIG → QuantLib → FinancePy deterministic EPE/ENE.
    """

    name = "ore"

    def __init__(self) -> None:
        ore_probe, ore_mod, ore_error = _probe_ore_swig()
        ore_ready = bool(ore_probe.available and ore_mod is not None and _is_ore_swig(ore_mod))
        # Prefer ORE alone when SWIG is present. Holding both QuantLib and ORE
        # module handles can abort on native teardown after some constructions.
        meta_ql, _ = probe_module("QuantLib")
        if ore_ready:
            ql_probe = VendorProbe(
                "QuantLib",
                meta_ql.available,
                meta_ql.version,
                meta_ql.module_path,
                None,
            )
            ql_mod = None
            quantlib_ready = True
            pricing = ore_mod
        else:
            ql_probe, ql_mod = meta_ql, None
            if meta_ql.available:
                _, ql_mod = probe_module("QuantLib")
            quantlib_ready = bool(
                ql_mod is not None
                and hasattr(ql_mod, "FlatForward")
                and hasattr(ql_mod, "FlatHazardRate")
            )
            pricing = ql_mod if quantlib_ready else None

        available = pricing is not None
        if ore_ready:
            version = ore_probe.version or ql_probe.version
            module_path = ore_probe.module_path
            error = None
        elif quantlib_ready:
            version = ql_probe.version
            module_path = ql_probe.module_path
            error = None
        else:
            version = None
            module_path = None
            error = ql_probe.error or ore_error or "QuantLib/ORE is not installed"

        self._probe = VendorProbe(
            name="ore",
            available=available,
            version=version,
            module_path=module_path,
            error=error,
        )
        self._quantlib_probe = ql_probe
        self._ore_probe = ore_probe
        self._quantlib = ql_mod if (quantlib_ready and not ore_ready) else None
        self._ore_swig = ore_mod if ore_ready else None
        self._ore_swig_error = None if ore_ready else ore_error
        self._pricing = pricing

    def initialize(self) -> VendorProbe:
        return self._probe

    @property
    def available(self) -> bool:
        return self._probe.available

    @property
    def ore_swig_available(self) -> bool:
        return self._ore_swig is not None

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self._probe.version,
            "error": self._probe.error,
            "role": "Complex derivatives, counterparty exposure and ORE/QuantLib-backed XVA",
            "pricing_backend": (
                "ORE" if self.ore_swig_available else ("QuantLib" if self._quantlib else None)
            ),
            "quantlib": {
                "available": bool(self._quantlib_probe.available),
                "version": self._quantlib_probe.version,
                "calls": list(QUANTLIB_CORE_CALLS),
                "error": self._quantlib_probe.error,
            },
            "ore_swig": {
                "available": self.ore_swig_available,
                "version": self._ore_probe.version,
                "path": self._ore_probe.module_path,
                "calls": list(ORE_CORE_CALLS),
                "error": None if self.ore_swig_available else self._ore_swig_error,
            },
            "fallback": "FinancePy FlatDiscountCurve EPE/ENE if QuantLib/ORE are absent",
            "trade_mapping": "Product → ORE trade descriptor in adapters/ore/trade.py (no OREApp XML)",
        }

    def discount_factor(self, zero_rate: float, years: float, value_date: date) -> float:
        """Continuous FlatForward DF. Does not construct bond or swaption instruments."""

        ql = self._ore_swig or self._quantlib
        horizon = max(float(years), 0.0)
        rate = max(float(zero_rate), -0.05)
        if ql is None:
            return math.exp(-rate * horizon)
        with _ql_evaluation(ql, value_date) as as_of_ql:
            day = ql.Actual365Fixed()
            curve = ql.FlatForward(
                as_of_ql,
                ql.QuoteHandle(ql.SimpleQuote(rate)),
                day,
                ql.Continuous,
            )
            curve.enableExtrapolation()
            grid = as_of_ql + int(round(horizon * 365.0))
            return float(curve.discount(grid))

    def map_snapshot(self, snapshot: Any) -> dict[str, Any]:
        """Translate platform holdings into ORE trade descriptors. No OREApp XML."""

        from ...products.assemble import product_from_holding
        from .trade import descriptor_from_product

        if self.ore_swig_available:
            curve_engine, curve_type = "ORE", "FlatForward"
        elif self._quantlib is not None:
            curve_engine, curve_type = "QuantLib", "FlatForward"
        else:
            curve_engine, curve_type = "FinancePy", "FlatDiscountCurve"
        trades = [descriptor_from_product(product_from_holding(position)) for position in snapshot.positions]
        return {
            "as_of": snapshot.as_of_date.isoformat(),
            "base_currency": snapshot.reporting_currency,
            "curves": [
                {
                    "name": f"{snapshot.reporting_currency}_DISCOUNT",
                    "type": curve_type,
                    "engine": curve_engine,
                }
            ],
            "trades": trades,
            "netting_sets": sorted({item["counterparty"] or "UNASSIGNED" for item in trades}),
            "ore_available": self.available,
            "ore_swig_available": self.ore_swig_available,
            "ore_app": False,
            "quantlib_version": self._quantlib_probe.version,
            "ore_version": self._ore_probe.version,
        }

    def price_product(self, product: Any, as_of: date, shocks: tuple[Any, ...] = ()) -> dict[str, Any]:
        """Price one OTC product. Zero-shock PV is platform MV; ORE supplies the delta."""

        from .pricing import price_product

        library = "ORE" if self.ore_swig_available else ("QuantLib" if self._quantlib is not None else "analytic")
        return price_product(self._pricing, product, as_of, tuple(shocks), library=library)

    def xva(
        self,
        snapshot: Any,
        financepy: Any,
        base_pv: float,
        *,
        counterparty_hazard: float,
        own_hazard: float,
        recovery_rate: float,
        funding_spread: float,
        initial_margin_pct: float,
        mva_funding_spread: float,
    ) -> dict[str, Any]:
        """CVA/DVA/FVA/MVA. ORE → QuantLib → FinancePy."""

        mapping = self.map_snapshot(snapshot)
        payload = {
            "snapshot": snapshot,
            "financepy": financepy,
            "base_pv": base_pv,
            "mapping": mapping,
            "counterparty_hazard": counterparty_hazard,
            "own_hazard": own_hazard,
            "recovery_rate": recovery_rate,
            "funding_spread": funding_spread,
            "initial_margin_pct": initial_margin_pct,
            "mva_funding_spread": mva_funding_spread,
        }
        if self.ore_swig_available:
            try:
                return self._curve_xva(library="ORE", ql=self._ore_swig, **payload)
            except Exception:  # noqa: BLE001 — published numbers stay on QuantLib path
                pass
        if self._quantlib is not None:
            try:
                return self._curve_xva(library="QuantLib", ql=self._quantlib, **payload)
            except Exception:  # noqa: BLE001 — published numbers stay on FinancePy path
                pass
        return self._deterministic_xva(**payload)

    def price_american_fx_future_option(
        self,
        *,
        future_price: float,
        strike: float,
        risk_free_rate: float,
        volatility: float,
        as_of: date,
        maturity: date,
        option_type: str = "Call",
        time_steps: int = 200,
    ) -> dict[str, Any]:
        """Black-76 American FX futures option via ORE binomial tree (CRR)."""

        ql = self._ore_swig or self._quantlib
        if ql is None:
            raise ImportError("ORE/QuantLib is required for American FX futures options")
        with _ql_evaluation(ql, as_of) as as_of_ql:
            maturity_ql = ql.Date(maturity.day, maturity.month, maturity.year)
            right = ql.Option.Call if option_type.lower().startswith("c") else ql.Option.Put
            payoff = ql.PlainVanillaPayoff(right, float(strike))
            exercise = ql.AmericanExercise(as_of_ql, maturity_ql)
            option = ql.VanillaOption(payoff, exercise)
            day = ql.Actual365Fixed()
            calendar = ql.NullCalendar()
            process = ql.BlackProcess(
                ql.QuoteHandle(ql.SimpleQuote(float(future_price))),
                ql.YieldTermStructureHandle(
                    ql.FlatForward(as_of_ql, float(risk_free_rate), day)
                ),
                ql.BlackVolTermStructureHandle(
                    ql.BlackConstantVol(as_of_ql, calendar, float(volatility), day)
                ),
            )
            option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", int(time_steps)))
            return {
                "library": "ORE" if self.ore_swig_available else "QuantLib",
                "model": "Black76_CRR_binomial",
                "npv": float(option.NPV()),
                "delta": float(option.delta()),
                "gamma": float(option.gamma()),
                "future_price": float(future_price),
                "strike": float(strike),
                "volatility": float(volatility),
                "risk_free_rate": float(risk_free_rate),
                "as_of": as_of.isoformat(),
                "maturity": maturity.isoformat(),
                "time_steps": int(time_steps),
            }

    def _curve_xva(
        self,
        *,
        library: str,
        ql: Any,
        snapshot: Any,
        financepy: Any,
        base_pv: float,
        mapping: dict[str, Any],
        counterparty_hazard: float,
        own_hazard: float,
        recovery_rate: float,
        funding_spread: float,
        initial_margin_pct: float,
        mva_funding_spread: float,
    ) -> dict[str, Any]:
        """Discounted EPE/ENE with ORE or QuantLib FlatForward + FlatHazardRate."""

        del financepy
        as_of: date = snapshot.as_of_date
        positive_pv = max(base_pv, 0.0)
        negative_pv = max(-base_pv, 0.0)
        max_maturity = max([position.duration for position in snapshot.positions] + [1.0])
        horizon = min(max(max_maturity, 1.0), 30.0)
        steps = 20
        dt = horizon / steps
        initial_margin = abs(snapshot.net_asset) * initial_margin_pct
        cva = dva = fva = mva = 0.0
        profile: list[dict[str, Any]] = []
        with _ql_evaluation(ql, as_of) as as_of_ql:
            day = ql.Actual365Fixed()
            curve = ql.FlatForward(
                as_of_ql,
                ql.QuoteHandle(ql.SimpleQuote(0.03)),
                day,
                ql.Continuous,
            )
            curve.enableExtrapolation()
            cp_curve = ql.FlatHazardRate(
                as_of_ql,
                ql.QuoteHandle(ql.SimpleQuote(counterparty_hazard)),
                day,
            )
            own_curve = ql.FlatHazardRate(
                as_of_ql,
                ql.QuoteHandle(ql.SimpleQuote(own_hazard)),
                day,
            )
            cp_curve.enableExtrapolation()
            own_curve.enableExtrapolation()
            previous_cp_survival = 1.0
            previous_own_survival = 1.0
            for index in range(1, steps + 1):
                time_years = index * dt
                grid = as_of_ql + int(round(time_years * 365.0))
                decay = max(1.0 - time_years / (horizon + dt), 0.0)
                epe = positive_pv * decay
                ene = negative_pv * decay + positive_pv * 0.05 * decay
                discount = float(curve.discount(grid))
                cp_survival = float(cp_curve.survivalProbability(grid))
                own_survival = float(own_curve.survivalProbability(grid))
                cp_default = previous_cp_survival - cp_survival
                own_default = previous_own_survival - own_survival
                cva += (1.0 - recovery_rate) * epe * cp_default * discount
                dva += (1.0 - recovery_rate) * ene * own_default * discount
                fva += epe * funding_spread * dt * discount
                mva += initial_margin * mva_funding_spread * dt * discount
                profile.append(
                    {
                        "time_years": time_years,
                        "epe": epe,
                        "ene": ene,
                        "discount_factor": discount,
                        "cp_survival": cp_survival,
                        "own_survival": own_survival,
                    }
                )
                previous_cp_survival = cp_survival
                previous_own_survival = own_survival
        calls = list(ORE_CORE_CALLS) if library == "ORE" else list(QUANTLIB_CORE_CALLS)
        return {
            "cva": cva,
            "dva": dva,
            "fva": fva,
            "mva": mva,
            "total_xva": cva - dva + fva + mva,
            "library": library,
            "parameters": {
                "counterparty_hazard": counterparty_hazard,
                "own_hazard": own_hazard,
                "recovery_rate": recovery_rate,
                "funding_spread": funding_spread,
                "initial_margin_pct": initial_margin_pct,
                "mva_funding_spread": mva_funding_spread,
            },
            "exposure_profile": profile,
            "ore_mapping": mapping,
            "quantlib_version": self._quantlib_probe.version,
            "ore_swig_available": self.ore_swig_available,
            "vendor_calls": calls,
            "methodology": (
                f"{library} FlatForward (continuous) + FlatHazardRate discounted EPE/ENE; "
                "full OREApp Monte Carlo netting/collateral remains an extension"
            ),
        }

    def _position_npvs(self, snapshot: Any) -> dict[str, float]:
        ql = self._pricing
        if ql is None:
            return {}
        priced: dict[str, float] = {}
        with _ql_evaluation(ql, snapshot.as_of_date) as as_of_ql:
            day = ql.Actual365Fixed()
            cal = ql.NullCalendar()
            for position in snapshot.positions:
                if not is_fixed_income(position):
                    continue
                try:
                    ytm = float(getattr(position, "ytm", 0.0) or 0.03)
                    if abs(ytm) >= 1.0:
                        ytm /= 100.0
                    curve = ql.FlatForward(
                        as_of_ql,
                        ql.QuoteHandle(ql.SimpleQuote(max(ytm, -0.05))),
                        day,
                        ql.Continuous,
                    )
                    curve.enableExtrapolation()
                    handle = ql.YieldTermStructureHandle(curve)
                    years = max(years_to_maturity(position, snapshot.as_of_date), 1.0 / 365.0)
                    maturity = as_of_ql + max(int(round(years * 365.0)), 1)
                    issue = as_of_ql - 365
                    coupon = coupon_rate(position)
                    schedule = ql.Schedule(
                        issue,
                        maturity,
                        ql.Period(ql.Annual),
                        cal,
                        ql.Unadjusted,
                        ql.Unadjusted,
                        ql.DateGeneration.Backward,
                        False,
                    )
                    bond = ql.FixedRateBond(0, 100.0, schedule, [coupon], day)
                    bond.setPricingEngine(ql.DiscountingBondEngine(handle))
                    scale = float(position.market_value_base) / 100.0
                    priced[position.security_code] = float(bond.NPV()) * scale
                except Exception:  # noqa: BLE001 — mapping must not fail on one bond
                    continue
        return priced

    def _deterministic_xva(
        self,
        snapshot: Any,
        financepy: Any,
        base_pv: float,
        mapping: dict[str, Any],
        *,
        counterparty_hazard: float,
        own_hazard: float,
        recovery_rate: float,
        funding_spread: float,
        initial_margin_pct: float,
        mva_funding_spread: float,
    ) -> dict[str, Any]:
        """FinancePy discounted EPE/ENE when QuantLib/ORE are absent."""

        positive_pv = max(base_pv, 0.0)
        negative_pv = max(-base_pv, 0.0)
        max_maturity = max([position.duration for position in snapshot.positions] + [1.0])
        horizon = min(max(max_maturity, 1.0), 30.0)
        steps = 20
        dt = horizon / steps
        cva = dva = fva = mva = 0.0
        profile = []
        previous_cp_survival = 1.0
        previous_own_survival = 1.0
        initial_margin = abs(snapshot.net_asset) * initial_margin_pct
        as_of = snapshot.as_of_date
        for index in range(1, steps + 1):
            time_years = index * dt
            decay = max(1.0 - time_years / (horizon + dt), 0.0)
            epe = positive_pv * decay
            ene = negative_pv * decay + positive_pv * 0.05 * decay
            discount = financepy.discount_factor(0.03, time_years, as_of)
            cp_survival = math.exp(-counterparty_hazard * time_years)
            own_survival = math.exp(-own_hazard * time_years)
            cp_default = previous_cp_survival - cp_survival
            own_default = previous_own_survival - own_survival
            cva += (1.0 - recovery_rate) * epe * cp_default * discount
            dva += (1.0 - recovery_rate) * ene * own_default * discount
            fva += epe * funding_spread * dt * discount
            mva += initial_margin * mva_funding_spread * dt * discount
            profile.append(
                {
                    "time_years": time_years,
                    "epe": epe,
                    "ene": ene,
                    "discount_factor": discount,
                }
            )
            previous_cp_survival = cp_survival
            previous_own_survival = own_survival
        return {
            "cva": cva,
            "dva": dva,
            "fva": fva,
            "mva": mva,
            "total_xva": cva - dva + fva + mva,
            "library": "FinancePy",
            "parameters": {
                "counterparty_hazard": counterparty_hazard,
                "own_hazard": own_hazard,
                "recovery_rate": recovery_rate,
                "funding_spread": funding_spread,
                "initial_margin_pct": initial_margin_pct,
                "mva_funding_spread": mva_funding_spread,
            },
            "exposure_profile": profile,
            "ore_mapping": mapping,
            "methodology": (
                "deterministic discounted exposure integration via FinancePy; "
                "ORE/QuantLib FlatForward/FlatHazardRate is used when installed"
            ),
        }
