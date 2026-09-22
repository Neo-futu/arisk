"""ORE-SWIG instrument pricing. No OREApp / XML workflow.

Platform market value stays the zero-shock PV. ORE supplies the shocked delta.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

from ...core.contracts import ProductKind


def _qld(ql: Any, value: date):
    return ql.Date(value.day, value.month, value.year)


@contextmanager
def _ql_evaluation(ql: Any, as_of: date) -> Iterator[Any]:
    settings = ql.Settings.instance()
    previous = ql.Date(settings.evaluationDate.serialNumber())
    as_of_ql = _qld(ql, as_of)
    settings.evaluationDate = as_of_ql
    try:
        yield as_of_ql
    finally:
        settings.evaluationDate = previous


def _kind(product: Any) -> str:
    return str(getattr(getattr(product, "kind", None), "value", getattr(product, "kind", "")))


def _ccy(ql: Any, code: str) -> Any:
    text = str(code or "USD").upper()
    parser = getattr(ql, "parseCurrency", None)
    if callable(parser):
        try:
            return parser(text)
        except Exception:  # noqa: BLE001
            pass
    ctor = getattr(ql, f"{text}Currency", None)
    if callable(ctor):
        return ctor()
    return ql.USDCurrency()


def _meta(product: Any) -> dict[str, Any]:
    return dict(getattr(product, "metadata", None) or {})


def _shifts(shocks: tuple[Any, ...]) -> dict[str, float]:
    out = {"rate": 0.0, "fx": 0.0, "vol": 0.0, "equity": 0.0, "spread": 0.0}
    for shock in shocks:
        key = str(getattr(shock.factor_type, "value", shock.factor_type))
        mode = str(getattr(shock.mode, "value", shock.mode))
        value = float(shock.value)
        if key == "RATE":
            out["rate"] += value
        elif key == "CREDIT_SPREAD":
            out["spread"] += value
        elif key == "FX":
            out["fx"] += value
        elif key == "EQUITY":
            out["equity"] += value
        elif key == "VOLATILITY":
            out["vol"] += value if mode == "RELATIVE" else value
    return out


def terms_of(product: Any) -> dict[str, Any]:
    meta = _meta(product)
    maturity = getattr(product, "maturity_date", None)
    return {
        "kind": _kind(product),
        "currency": str(getattr(product, "currency", "") or meta.get("currency") or "USD"),
        "notional": float(getattr(product, "notional", 0.0) or getattr(product, "market_value_base", 0.0) or 0.0),
        "market_value_base": float(getattr(product, "market_value_base", 0.0) or 0.0),
        "strike": float(getattr(product, "strike", 0.0) or meta.get("strike") or 0.0),
        "volatility": float(getattr(product, "volatility", 0.0) or meta.get("volatility") or 0.20),
        "option_type": str(getattr(product, "option_type", "") or meta.get("option_type") or "Call"),
        "exercise": str(getattr(product, "exercise", "") or meta.get("exercise") or "European"),
        "pair": str(getattr(product, "pair", "") or meta.get("pair") or ""),
        "spot": float(getattr(product, "spot", 0.0) or meta.get("spot") or getattr(product, "fx_rate", 0.0) or 1.0),
        "domestic_rate": float(getattr(product, "domestic_rate", 0.0) or meta.get("domestic_rate") or 0.03),
        "foreign_rate": float(getattr(product, "foreign_rate", 0.0) or meta.get("foreign_rate") or 0.03),
        "hazard_rate": float(getattr(product, "hazard_rate", 0.0) or meta.get("hazard_rate") or 0.01),
        "recovery_rate": float(getattr(product, "recovery_rate", 0.0) or meta.get("recovery_rate") or 0.40),
        "pay_fixed": bool(getattr(product, "pay_fixed", True)),
        "protection_seller": bool(getattr(product, "protection_seller", False)),
        "tenor_years": float(getattr(product, "tenor_years", 0.0) or meta.get("tenor_years") or 5.0),
        "option_tenor_years": float(
            getattr(product, "option_tenor_years", 0.0) or meta.get("option_tenor_years") or 1.0
        ),
        "maturity": maturity,
        "underlying": str(getattr(product, "underlying", "") or meta.get("underlying") or "EQUITY"),
    }


def _pair_currencies(ql: Any, terms: dict[str, Any]) -> tuple[Any, Any]:
    pair = str(terms.get("pair") or "")
    if len(pair) >= 6:
        return _ccy(ql, pair[:3]), _ccy(ql, pair[3:6])
    domestic = _ccy(ql, terms["currency"])
    other = _ccy(ql, "USD" if terms["currency"] != "USD" else "EUR")
    return other, domestic


def _flat_forward(ql: Any, as_of_ql: Any, rate: float) -> Any:
    day = ql.Actual365Fixed()
    curve = ql.FlatForward(as_of_ql, ql.QuoteHandle(ql.SimpleQuote(float(rate))), day, ql.Continuous)
    curve.enableExtrapolation()
    return curve


def _flat_curve(ql: Any, as_of_ql: Any, rate: float) -> Any:
    return ql.YieldTermStructureHandle(_flat_forward(ql, as_of_ql, rate))


def _grid(as_of_ql: Any, years: float) -> Any:
    return as_of_ql + int(round(max(float(years), 0.0) * 365.0))


def _right(ql: Any, option_type: str) -> Any:
    return ql.Option.Call if str(option_type).lower().startswith("c") else ql.Option.Put


def _vanilla_npv(
    ql: Any,
    *,
    as_of_ql: Any,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    maturity: date,
    option_type: str,
    american: bool,
) -> float:
    strike_px = float(strike or spot)
    vol = max(float(vol), 1e-6)
    mat = _qld(ql, maturity)
    payoff = ql.PlainVanillaPayoff(_right(ql, option_type), strike_px)
    exercise = ql.AmericanExercise(as_of_ql, mat) if american else ql.EuropeanExercise(mat)
    option = ql.VanillaOption(payoff, exercise)
    day = ql.Actual365Fixed()
    calendar = ql.NullCalendar()
    process = ql.BlackProcess(
        ql.QuoteHandle(ql.SimpleQuote(float(spot))),
        _flat_curve(ql, as_of_ql, rate),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(as_of_ql, calendar, vol, day)),
    )
    if american:
        option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", 80))
    else:
        option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return float(option.NPV())


def _fx_forward_npv(ql: Any, as_of_ql: Any, terms: dict[str, Any], spot: float, rd: float, rf: float) -> float:
    ccy1, ccy2 = _pair_currencies(ql, terms)
    notional = float(terms["notional"] or 1.0)
    strike = float(terms["strike"] or spot or 1.0)
    maturity = terms["maturity"]
    mat = _qld(ql, maturity) if maturity is not None else as_of_ql + 365
    fwd = ql.FxForward(notional, ccy1, notional * strike, ccy2, mat, True)
    engine = ql.DiscountingFxForwardEngine(
        ccy1,
        _flat_curve(ql, as_of_ql, rf),
        ccy2,
        _flat_curve(ql, as_of_ql, rd),
        ql.QuoteHandle(ql.SimpleQuote(float(spot))),
    )
    fwd.setPricingEngine(engine)
    return float(fwd.NPV())


def _irs_npv(ql: Any, as_of_ql: Any, terms: dict[str, Any], rate: float) -> float:
    curve = _flat_curve(ql, as_of_ql, rate)
    idx = ql.USDLibor(ql.Period(3, ql.Months), curve)
    years = max(int(round(float(terms["tenor_years"]))), 1)
    strike = float(terms["strike"] or rate)
    swap = ql.MakeVanillaSwap(ql.Period(years, ql.Years), idx, strike)
    swap.setPricingEngine(ql.DiscountingSwapEngine(curve))
    sign = 1.0 if terms["pay_fixed"] else -1.0
    return float(swap.NPV()) * sign * float(terms["notional"] or 1.0)


def _swaption_npv(ql: Any, as_of_ql: Any, terms: dict[str, Any], rate: float, vol: float) -> float:
    """Payer/receiver swaption via ORE FlatForward annuity + blackFormula."""

    curve = _flat_forward(ql, as_of_ql, rate)
    n_opt = max(int(round(float(terms["option_tenor_years"]))), 1)
    n_swap = max(int(round(float(terms["tenor_years"]))), 1)
    df_start = float(curve.discount(_grid(as_of_ql, n_opt)))
    df_end = float(curve.discount(_grid(as_of_ql, n_opt + n_swap)))
    annuity = 0.0
    for k in range(1, n_swap + 1):
        annuity += float(curve.discount(_grid(as_of_ql, n_opt + k)))
    annuity = max(annuity, 1e-12)
    forward = (df_start - df_end) / annuity
    strike = float(terms["strike"] or forward)
    std_dev = max(float(vol), 1e-6) * math.sqrt(float(n_opt))
    right = ql.Option.Call if terms["pay_fixed"] else ql.Option.Put
    unit = float(ql.blackFormula(right, strike, forward, std_dev, annuity))
    return unit * float(terms["notional"] or 1.0)


def _cds_npv(ql: Any, as_of_ql: Any, terms: dict[str, Any], rate: float, hazard: float) -> float:
    """Mid-point CDS via ORE FlatForward + FlatHazardRate (same curves as XVA)."""

    day = ql.Actual365Fixed()
    disc = _flat_forward(ql, as_of_ql, rate)
    hz = ql.FlatHazardRate(as_of_ql, ql.QuoteHandle(ql.SimpleQuote(max(float(hazard), 1e-8))), day)
    hz.enableExtrapolation()
    years = max(float(terms["tenor_years"] or 5.0), 0.25)
    steps = max(int(round(years * 4.0)), 1)
    dt = years / steps
    recovery = float(terms["recovery_rate"])
    coupon = float(terms["strike"] or 0.01)
    prev_s = 1.0
    protection = 0.0
    rpv01 = 0.0
    for index in range(1, steps + 1):
        grid = _grid(as_of_ql, index * dt)
        df = float(disc.discount(grid))
        surv = float(hz.survivalProbability(grid))
        protection += (1.0 - recovery) * max(prev_s - surv, 0.0) * df
        rpv01 += dt * df * 0.5 * (prev_s + surv)
        prev_s = surv
    npv = protection - coupon * rpv01
    if terms["protection_seller"]:
        npv = -npv
    return npv * float(terms["notional"] or 1.0)


def _model_npv(ql: Any, as_of_ql: Any, terms: dict[str, Any], shifts: dict[str, float], shocked: bool) -> float:
    kind = terms["kind"]
    rate = float(terms["domestic_rate"]) + (shifts["rate"] if shocked else 0.0)
    rf = float(terms["foreign_rate"])
    vol = float(terms["volatility"])
    if shocked:
        vol = max(vol * (1.0 + shifts["vol"]), 1e-6) if abs(shifts["vol"]) < 5 else max(vol + shifts["vol"], 1e-6)
    spot = float(terms["spot"] or 1.0)
    if shocked:
        if kind in {ProductKind.OPTION.value, ProductKind.FUTURE.value}:
            spot *= 1.0 + shifts["equity"]
        if kind in {
            ProductKind.FX.value,
            ProductKind.FX_FORWARD.value,
            ProductKind.FX_OPTION.value,
            ProductKind.FUTURE.value,
        }:
            spot *= 1.0 + shifts["fx"]
    hazard = float(terms["hazard_rate"]) + ((shifts["spread"] / max(1.0 - float(terms["recovery_rate"]), 0.2)) if shocked else 0.0)
    maturity = terms["maturity"] or date(
        as_of_ql.year() + max(int(round(float(terms["tenor_years"]))), 1),
        as_of_ql.month(),
        min(as_of_ql.dayOfMonth(), 28),
    )

    if kind == ProductKind.FX.value:
        base_spot = max(float(terms["spot"] or spot), 1e-12)
        return float(terms["market_value_base"]) * (spot / base_spot)
    if kind == ProductKind.FUTURE.value:
        return float(terms["market_value_base"]) * (spot / max(float(terms["spot"] or 1.0), 1e-12))
    if kind == ProductKind.FX_FORWARD.value:
        return _fx_forward_npv(ql, as_of_ql, terms, spot, rate, rf)
    if kind == ProductKind.FX_OPTION.value:
        american = str(terms["exercise"]).lower().startswith("a")
        unit = _vanilla_npv(
            ql,
            as_of_ql=as_of_ql,
            spot=spot,
            strike=terms["strike"] or spot,
            rate=rate,
            vol=vol,
            maturity=maturity,
            option_type=terms["option_type"],
            american=american,
        )
        return unit * float(terms["notional"] or 1.0)
    if kind == ProductKind.OPTION.value:
        unit = _vanilla_npv(
            ql,
            as_of_ql=as_of_ql,
            spot=spot or 100.0,
            strike=terms["strike"] or spot or 100.0,
            rate=rate,
            vol=vol,
            maturity=maturity,
            option_type=terms["option_type"],
            american=str(terms["exercise"]).lower().startswith("a"),
        )
        return unit * float(terms["notional"] or 1.0)
    if kind in {ProductKind.IRS.value, ProductKind.SWAP.value}:
        return _irs_npv(ql, as_of_ql, terms, rate)
    if kind == ProductKind.SWAPTION.value:
        return _swaption_npv(ql, as_of_ql, terms, rate, vol)
    if kind == ProductKind.CDS.value:
        return _cds_npv(ql, as_of_ql, terms, rate, hazard)
    return float(terms["market_value_base"])


def _analytic_delta(terms: dict[str, Any], shifts: dict[str, float]) -> float:
    """Fallback when a native ORE construction fails. Zero at no shock."""

    kind = terms["kind"]
    notional = float(terms["notional"] or terms["market_value_base"] or 0.0)
    years = max(float(terms["tenor_years"] or 1.0), 0.0)
    mv = float(terms["market_value_base"] or 0.0)
    if kind == ProductKind.FX.value:
        return mv * shifts["fx"]
    if kind == ProductKind.FUTURE.value:
        return mv * (shifts["equity"] + shifts["fx"] - years * shifts["rate"])
    if kind in {ProductKind.FX_FORWARD.value, ProductKind.IRS.value, ProductKind.SWAP.value}:
        sign = 1.0 if terms.get("pay_fixed", True) else -1.0
        return sign * (-notional * years) * shifts["rate"] + mv * shifts["fx"]
    if kind == ProductKind.SWAPTION.value:
        return (-notional * years) * shifts["rate"] + 0.4 * notional * (years ** 0.5) * shifts["vol"]
    if kind == ProductKind.CDS.value:
        sign = -1.0 if terms.get("protection_seller") else 1.0
        return sign * notional * years * shifts["spread"]
    if kind in {ProductKind.FX_OPTION.value, ProductKind.OPTION.value}:
        return mv * (shifts["fx"] + shifts["equity"] + 0.4 * shifts["vol"])
    return 0.0


def price_product(ql: Any, product: Any, as_of: date, shocks: tuple[Any, ...] = (), *, library: str = "ORE") -> dict[str, Any]:
    terms = terms_of(product)
    shifts = _shifts(shocks)
    mv = float(terms["market_value_base"])
    trade_type = terms["kind"]
    native = False
    model_base = model_shocked = 0.0
    if ql is not None:
        try:
            with _ql_evaluation(ql, as_of) as as_of_ql:
                model_base = _model_npv(ql, as_of_ql, terms, shifts, False)
                model_shocked = _model_npv(ql, as_of_ql, terms, shifts, True) if shocks else model_base
            native = True
        except Exception:  # noqa: BLE001 — keep valuation available
            native = False
    if native:
        shocked_pv = mv + (model_shocked - model_base)
    else:
        shocked_pv = mv + _analytic_delta(terms, shifts)
    return {
        "base_pv": mv,
        "shocked_pv": float(shocked_pv),
        "pnl": float(shocked_pv) - mv,
        "model_npv": float(model_base) if native else None,
        "library": library if native else "analytic",
        "trade_type": trade_type,
        "ore_app": False,
        "cashflows": [{"type": "otc", "kind": trade_type, "amount": mv}],
    }
