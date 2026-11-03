"""FinancePy adapter — the only RiskEngine module that imports financepy."""
from __future__ import annotations

from datetime import date
from typing import Any

from ..vendor import VendorProbe, probe_module

FINANCEPY_FLAT_CURVE_CLASS = "financepy.market.curves.flat_discount_curve.FlatDiscountCurve"
FINANCEPY_CORE_CALLS = [
    "financepy.utils.date.Date",
    FINANCEPY_FLAT_CURVE_CLASS,
    "FlatDiscountCurve.df_t",
    "FlatDiscountCurve.bump_parallel",
]


class FinancePyAdapter:
    """Build and shock FinancePy curves. Vendor objects stay inside this class."""

    name = "financepy"

    def __init__(self, value_date: date | None = None):
        self.value_date = value_date
        self._probe, self._module = probe_module("financepy")
        self._curve_class_path = FINANCEPY_FLAT_CURVE_CLASS
        self._Date = None
        self._Curve = None
        if self._probe.available:
            self._load_symbols()

    def _load_symbols(self) -> None:
        date_mod = probe_module("financepy.utils.date")[1]
        self._Date = getattr(date_mod, "Date", None) if date_mod is not None else None
        curve_probe, curve_mod = probe_module("financepy.market.curves.flat_discount_curve")
        if curve_probe.available and curve_mod is not None:
            self._Curve = getattr(curve_mod, "FlatDiscountCurve", None)
            self._curve_class_path = FINANCEPY_FLAT_CURVE_CLASS
            return
        legacy_probe, legacy_mod = probe_module("financepy.market.curves.discount_curve_flat")
        if legacy_probe.available and legacy_mod is not None:
            self._Curve = getattr(legacy_mod, "DiscountCurveFlat", None)
            self._curve_class_path = "financepy.market.curves.discount_curve_flat.DiscountCurveFlat"

    def initialize(self) -> VendorProbe:
        return self._probe

    @property
    def available(self) -> bool:
        return bool(self._probe.available and self._Date is not None and self._Curve is not None)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self._probe.version,
            "curve_class": self._curve_class_path,
            "error": self._probe.error,
        }

    def _require(self) -> None:
        if not self.available:
            raise ImportError("FinancePy is not installed in the processing runtime")

    def _finance_date(self, value_date: date):
        self._require()
        return self._Date(value_date.day, value_date.month, value_date.year)

    def flat_curve(self, zero_rate: float, value_date: date | None = None) -> Any:
        """Build a continuously-compounded FinancePy flat discount curve."""

        self._require()
        as_of = value_date or self.value_date
        if as_of is None:
            raise ValueError("value_date is required to build a FinancePy curve")
        return self._Curve(self._finance_date(as_of), max(float(zero_rate), -0.05))

    def discount_factor(self, zero_rate: float, years: float, value_date: date | None = None) -> float:
        """Call FinancePy ``df_t`` for a cash-flow horizon."""

        return float(self.flat_curve(zero_rate, value_date).df_t(max(float(years), 0.0)))

    def shocked_discount_factor(
        self,
        zero_rate: float,
        shock: float,
        years: float,
        value_date: date | None = None,
    ) -> float:
        """Call FinancePy ``bump_parallel`` then ``df_t`` for shocked valuation."""

        base_curve = self.flat_curve(zero_rate, value_date)
        base_rate = max(float(zero_rate), -0.05)
        shocked_rate = max(float(zero_rate) + float(shock), -0.05)
        shocked_curve = base_curve.bump_parallel(shocked_rate - base_rate)
        return float(shocked_curve.df_t(max(float(years), 0.0)))

    def modified_duration(
        self,
        zero_rate: float,
        years: float,
        value_date: date | None = None,
        bump: float = 0.0001,
    ) -> float:
        """Central-difference duration from FinancePy discount factors (bp bump)."""

        up = self.shocked_discount_factor(zero_rate, bump, years, value_date)
        down = self.shocked_discount_factor(zero_rate, -bump, years, value_date)
        base = self.discount_factor(zero_rate, years, value_date)
        if not base:
            return 0.0
        return float(-(up - down) / (2.0 * bump) / base)

    def reprice_from_ytm(
        self,
        zero_rate: float,
        years: float,
        market_value_base: float,
        shock: float = 0.0,
        value_date: date | None = None,
    ) -> float:
        """Identity-calibrated FinancePy reprice: implied CF discounted on a shocked flat curve."""

        as_of = value_date or self.value_date
        base_df = self.discount_factor(zero_rate, years, as_of)
        terminal = float(market_value_base) / base_df if base_df else float(market_value_base)
        return float(terminal * self.shocked_discount_factor(zero_rate, shock, years, as_of))

    def repo_carry(
        self,
        repo_rate: float,
        years: float,
        market_value_base: float,
        shock: float = 0.0,
        haircut: float = 0.0,
        value_date: date | None = None,
    ) -> float:
        """Repo / reverse-repo carry. Zero-shock identity = book MV; rate bump uses flat DF."""

        del haircut  # haircut is audited on cashflows / liquidity; PV identity stays on book
        if abs(float(shock)) < 1e-15:
            return float(market_value_base)
        return self.reprice_from_ytm(repo_rate, years, market_value_base, shock, value_date)


class FinancePyValuationAdapter(FinancePyAdapter):
    """Compatibility name used by existing Risk Testing reports."""

    def __init__(self, value_date: date):
        super().__init__(value_date)


def financepy_usage(
    business_module: str,
    direct_calls: list[str] | None = None,
    supplementary_engine: str | None = None,
) -> dict[str, Any]:
    """Return an auditable implementation descriptor for API and GUI reports."""

    return {
        "business_module": business_module,
        "valuation_adapter": "risk_testing.financepy_adapter.FinancePyValuationAdapter",
        "financepy_calls": direct_calls if direct_calls is not None else list(FINANCEPY_CORE_CALLS),
        "supplementary_engine": supplementary_engine,
        "portfolio_data_module": "risk_testing.portfolio_data",
        "market_data_module": "risk_testing.market_data",
    }


def core_calls() -> list[str]:
    adapter = FinancePyAdapter()
    calls = list(FINANCEPY_CORE_CALLS)
    if adapter._curve_class_path != FINANCEPY_FLAT_CURVE_CLASS:
        calls[1] = adapter._curve_class_path
    return calls
