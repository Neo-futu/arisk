"""FinancePy-powered revaluation and professional portfolio risk analytics."""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Iterable

import numpy as np

from .financepy_adapter import FinancePyValuationAdapter
from .models import PortfolioSnapshot, Position, RiskFactorType, Scenario, Shock, ShockMode


KRD_BUCKETS: tuple[tuple[str, float], ...] = (
    ("1M", 1 / 12), ("3M", 0.25), ("6M", 0.5), ("1Y", 1.0),
    ("2Y", 2.0), ("3Y", 3.0), ("5Y", 5.0), ("10Y", 10.0), ("20Y+", 20.0),
)


class ProfessionalRiskEngine:
    """Run ORE-style risk workflows on an existing ARISK portfolio snapshot."""

    engine_name = "FinancePy Professional Risk Engine"

    def __init__(self, snapshot: PortfolioSnapshot):
        self.snapshot = snapshot
        self.financepy = FinancePyValuationAdapter(snapshot.as_of_date)

    def _bucket(self, position: Position) -> str:
        years = position.duration
        if position.maturity_date is not None:
            years = max(
                (position.maturity_date - self.snapshot.as_of_date).days / 365.0,
                position.duration,
            )
        for label, boundary in KRD_BUCKETS:
            if years <= boundary:
                return label
        return "20Y+"

    def _discount(self, rate: float, years: float) -> float:
        """Discount with FinancePy rather than a local pricing formula."""

        return self.financepy.discount_factor(rate, years)

    def _position_value(self, position: Position, shocks: Iterable[Shock]) -> float:
        value = float(position.market_value_base)
        rate_shift = 0.0
        spread_shift = 0.0
        equity_relative = 0.0
        fx_relative = 0.0
        vol_relative = 0.0
        for shock in shocks:
            if shock.currency and shock.currency != position.currency:
                continue
            if shock.tenor and shock.tenor != self._bucket(position):
                continue
            if shock.factor_type == RiskFactorType.RATE:
                rate_shift += shock.value
            elif shock.factor_type == RiskFactorType.CREDIT_SPREAD:
                spread_shift += shock.value
            elif shock.factor_type == RiskFactorType.EQUITY:
                equity_relative += shock.value
            elif shock.factor_type == RiskFactorType.FX:
                fx_relative += shock.value
            elif shock.factor_type == RiskFactorType.VOLATILITY:
                vol_relative += shock.value

        if position.asset_class in {"BOND", "CD", "DEPOSIT"}:
            years = position.duration
            if position.maturity_date is not None:
                years = max((position.maturity_date - self.snapshot.as_of_date).days / 365.0, 1 / 365)
            base_rate = position.ytm if abs(position.ytm) < 1.0 else position.ytm / 100.0
            base_df = self._discount(base_rate, years)
            terminal_cashflow = value / base_df if base_df else value
            shocked_df = self.financepy.shocked_discount_factor(
                base_rate,
                rate_shift + spread_shift,
                years,
            )
            value = terminal_cashflow * shocked_df
        elif position.asset_class in {"EQUITY", "FUND"}:
            value *= 1.0 + equity_relative
            observed_volatility = float(position.metadata.get("historical_volatility", 0.20))
            # Transparent vega proxy until an option-specific FinancePy adapter is supplied.
            value += position.market_value_base * observed_volatility * 0.40 * vol_relative

        if position.currency != self.snapshot.reporting_currency:
            value *= 1.0 + fx_relative
        return float(value)

    def value(self, shocks: Iterable[Shock] = ()) -> dict[str, Any]:
        """Return portfolio and trade-level PV under a shock set."""

        shock_tuple = tuple(shocks)
        trade_values = [
            {
                "security_code": position.security_code,
                "security_name": position.security_name,
                "asset_class": position.asset_class,
                "base_pv": position.market_value_base,
                "shocked_pv": self._position_value(position, shock_tuple),
                "pnl": self._position_value(position, shock_tuple) - position.market_value_base,
            }
            for position in self.snapshot.positions
        ]
        base_pv = sum(item["base_pv"] for item in trade_values)
        shocked_pv = sum(item["shocked_pv"] for item in trade_values)
        return {
            "base_pv": base_pv,
            "shocked_pv": shocked_pv,
            "pnl": shocked_pv - base_pv,
            "pnl_pct_nav": (shocked_pv - base_pv) / self.snapshot.net_asset * 100.0 if self.snapshot.net_asset else None,
            "trade_values": sorted(trade_values, key=lambda item: abs(item["pnl"]), reverse=True),
        }

    def sensitivity(self, shocks: Iterable[Shock]) -> dict[str, Any]:
        """Run one-factor-at-a-time PV/Delta/Gamma sensitivity tests."""

        rows: list[dict[str, Any]] = []
        for shock in shocks:
            up = self.value((shock,))
            down_shock = Shock(shock.factor_type, -shock.value, shock.mode, shock.tenor, shock.currency, shock.label)
            down = self.value((down_shock,))
            denominator = shock.value if shock.value else 1.0
            rows.append({
                "factor_type": shock.factor_type.value,
                "label": shock.label or shock.factor_type.value,
                "tenor": shock.tenor,
                "currency": shock.currency,
                "shock": shock.value,
                "mode": shock.mode.value,
                "up_pnl": up["pnl"],
                "down_pnl": down["pnl"],
                "delta": (up["pnl"] - down["pnl"]) / (2.0 * denominator),
                "gamma": (up["pnl"] + down["pnl"]) / (denominator * denominator),
                "pnl_pct_nav": up["pnl_pct_nav"],
            })
        return self._report("SENSITIVITY", {"sensitivities": rows})

    def scenario(self, scenario: Scenario) -> dict[str, Any]:
        """Revalue all positions under simultaneous scenario shocks."""

        valuation = self.value(scenario.shocks)
        return self._report("SCENARIO", {
            "scenario": {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "category": scenario.category,
                "description": scenario.description,
                "shocks": [{**asdict(shock), "factor_type": shock.factor_type.value, "mode": shock.mode.value} for shock in scenario.shocks],
            },
            **valuation,
        })

    def reverse_stress(self, scenario: Scenario, target_loss_pct_nav: float, max_scale: float = 20.0) -> dict[str, Any]:
        """Find the smallest proportional scenario scale that breaches a target loss."""

        target_loss = abs(target_loss_pct_nav) / 100.0 * self.snapshot.net_asset
        low, high = 0.0, max_scale
        high_result = self.value(self._scale_shocks(scenario.shocks, high))
        reached = -high_result["pnl"] >= target_loss
        iterations = 0
        if reached:
            for _ in range(60):
                iterations += 1
                middle = (low + high) / 2.0
                result = self.value(self._scale_shocks(scenario.shocks, middle))
                if -result["pnl"] >= target_loss:
                    high = middle
                else:
                    low = middle
            final = self.value(self._scale_shocks(scenario.shocks, high))
        else:
            final = high_result
        return self._report("REVERSE_STRESS", {
            "scenario_id": scenario.scenario_id,
            "target_loss_pct_nav": abs(target_loss_pct_nav),
            "target_loss_amount": target_loss,
            "breach_reached": reached,
            "critical_scale": high if reached else None,
            "tested_max_scale": max_scale,
            "iterations": iterations,
            "critical_shocks": [
                {**asdict(shock), "factor_type": shock.factor_type.value, "mode": shock.mode.value}
                for shock in self._scale_shocks(scenario.shocks, high)
            ],
            **final,
        })

    @staticmethod
    def _scale_shocks(shocks: Iterable[Shock], scale: float) -> tuple[Shock, ...]:
        return tuple(Shock(s.factor_type, s.value * scale, s.mode, s.tenor, s.currency, s.label) for s in shocks)

    def tail_risk(self, sigma_levels: Iterable[float], capital_buffer: float) -> dict[str, Any]:
        """Calculate historical ES and 3σ–5σ black-swan capital impacts."""

        returns = np.asarray([item[1] for item in self.snapshot.nav_returns], dtype=float)
        if returns.size < 2:
            return self._report("TAIL_RISK", {"status": "INSUFFICIENT_DATA", "tail_scenarios": []})
        mean = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))
        var_return = float(np.percentile(returns, 1.0))
        tail = returns[returns <= var_return]
        expected_shortfall = float(np.mean(tail)) if tail.size else var_return
        scenarios = []
        for level in sigma_levels:
            shock_return = mean - abs(level) * sigma
            loss = max(-shock_return * self.snapshot.net_asset, 0.0)
            scenarios.append({
                "sigma": abs(level),
                "shock_return_pct": shock_return * 100.0,
                "loss_amount": loss,
                "loss_pct_nav": loss / self.snapshot.net_asset * 100.0 if self.snapshot.net_asset else None,
                "capital_after": capital_buffer - loss,
                "capital_adequacy_pct": (capital_buffer - loss) / self.snapshot.net_asset * 100.0 if self.snapshot.net_asset else None,
                "capital_breached": loss > capital_buffer,
            })
        return self._report("TAIL_RISK", {
            "status": "OK",
            "sample_size": int(returns.size),
            "daily_mean_pct": mean * 100.0,
            "daily_volatility_pct": sigma * 100.0,
            "historical_var_99_amount": abs(var_return * self.snapshot.net_asset),
            "expected_shortfall_99_amount": abs(expected_shortfall * self.snapshot.net_asset),
            "tail_scenarios": scenarios,
        })

    def krd(self, bump_bps: float = 1.0) -> dict[str, Any]:
        """Calculate key-rate PV01 and duration by maturity bucket."""

        shock_size = bump_bps / 10000.0
        base_pv = self.value()["base_pv"]
        rows = []
        for label, _boundary in KRD_BUCKETS:
            result = self.value((Shock(RiskFactorType.RATE, shock_size, ShockMode.ABSOLUTE, tenor=label, label=label),))
            pv01 = result["pnl"]
            rows.append({
                "tenor": label,
                "bump_bps": bump_bps,
                "pv01": pv01,
                "key_rate_duration": -pv01 / (base_pv * shock_size) if base_pv and shock_size else 0.0,
            })
        return self._report("KRD", {
            "base_pv": base_pv,
            "portfolio_pv01": sum(item["pv01"] for item in rows),
            "buckets": rows,
        })

    def var_backtest(self, confidence: float = 0.99, window: int = 60) -> dict[str, Any]:
        """Rolling historical VaR backtest with Kupiec unconditional coverage."""

        observations = self.snapshot.nav_returns
        returns = np.asarray([item[1] for item in observations], dtype=float)
        if returns.size <= window:
            return self._report("VAR_BACKTEST", {"status": "INSUFFICIENT_DATA", "observations": int(returns.size), "points": []})
        points = []
        exceptions = 0
        alpha = 1.0 - confidence
        for index in range(window, len(returns)):
            sample = returns[index - window:index]
            var_return = float(np.percentile(sample, alpha * 100.0))
            sample_tail = sample[sample <= var_return]
            cvar_return = float(np.mean(sample_tail)) if sample_tail.size else var_return
            actual = float(returns[index])
            breached = actual < var_return
            exceptions += int(breached)
            points.append({
                "date": observations[index][0].isoformat(),
                "actual_pnl": actual * self.snapshot.net_asset,
                "var_limit": abs(var_return * self.snapshot.net_asset),
                "cvar_limit": abs(cvar_return * self.snapshot.net_asset),
                "actual_return_pct": actual * 100.0,
                "var_return_pct": abs(var_return) * 100.0,
                "exception": breached,
            })
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
        return self._report("VAR_BACKTEST", {
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
        })

    def xva(
        self,
        counterparty_hazard: float,
        own_hazard: float,
        recovery_rate: float,
        funding_spread: float,
        initial_margin_pct: float,
        mva_funding_spread: float,
    ) -> dict[str, Any]:
        """Compute transparent deterministic CVA/DVA/FVA/MVA exposure integration."""

        positive_pv = max(self.value()["base_pv"], 0.0)
        negative_pv = max(-self.value()["base_pv"], 0.0)
        max_maturity = max([position.duration for position in self.snapshot.positions] + [1.0])
        horizon = min(max(max_maturity, 1.0), 30.0)
        steps = 20
        dt = horizon / steps
        cva = dva = fva = mva = 0.0
        profile = []
        previous_cp_survival = 1.0
        previous_own_survival = 1.0
        initial_margin = abs(self.snapshot.net_asset) * initial_margin_pct
        for index in range(1, steps + 1):
            time_years = index * dt
            decay = max(1.0 - time_years / (horizon + dt), 0.0)
            epe = positive_pv * decay
            ene = negative_pv * decay + positive_pv * 0.05 * decay
            discount = self.financepy.discount_factor(0.03, time_years)
            cp_survival = math.exp(-counterparty_hazard * time_years)
            own_survival = math.exp(-own_hazard * time_years)
            cp_default = previous_cp_survival - cp_survival
            own_default = previous_own_survival - own_survival
            cva += (1.0 - recovery_rate) * epe * cp_default * discount
            dva += (1.0 - recovery_rate) * ene * own_default * discount
            fva += epe * funding_spread * dt * discount
            mva += initial_margin * mva_funding_spread * dt * discount
            profile.append({"time_years": time_years, "epe": epe, "ene": ene, "discount_factor": discount})
            previous_cp_survival = cp_survival
            previous_own_survival = own_survival
        return self._report("XVA", {
            "cva": cva,
            "dva": dva,
            "fva": fva,
            "mva": mva,
            "total_xva": cva - dva + fva + mva,
            "parameters": {
                "counterparty_hazard": counterparty_hazard,
                "own_hazard": own_hazard,
                "recovery_rate": recovery_rate,
                "funding_spread": funding_spread,
                "initial_margin_pct": initial_margin_pct,
                "mva_funding_spread": mva_funding_spread,
            },
            "exposure_profile": profile,
            "methodology": "deterministic discounted exposure integration; netting/collateral simulation is an extension point",
        })

    def pnl_explain(self, previous: PortfolioSnapshot) -> dict[str, Any]:
        """Explain snapshot-to-snapshot PnL by carry, rates, FX, position and residual."""

        prior = {item.security_code: item for item in previous.positions}
        current = {item.security_code: item for item in self.snapshot.positions}
        days = max((self.snapshot.as_of_date - previous.as_of_date).days, 1)
        rows = []
        totals = {"carry": 0.0, "rates": 0.0, "fx": 0.0, "position": 0.0, "residual": 0.0, "total": 0.0}
        for code in sorted(set(prior) | set(current)):
            old = prior.get(code)
            new = current.get(code)
            old_pv = old.market_value_base if old else 0.0
            new_pv = new.market_value_base if new else 0.0
            total = new_pv - old_pv
            reference = new or old
            carry = (old_pv * reference.coupon_rate * days / 365.0) if reference else 0.0
            rate_change = ((new.ytm - old.ytm) if old and new else 0.0)
            if abs(rate_change) > 1.0:
                rate_change /= 100.0
            rates = -old_pv * (old.duration if old else 0.0) * rate_change
            fx_change = ((new.fx_rate / old.fx_rate - 1.0) if old and new and old.fx_rate else 0.0)
            fx = old_pv * fx_change if reference and reference.currency != self.snapshot.reporting_currency else 0.0
            position_effect = total if old is None or new is None else (new.market_value - old.market_value) * new.fx_rate
            residual = total - carry - rates - fx - position_effect
            item = {"security_code": code, "total_pnl": total, "carry": carry, "rates": rates, "fx": fx, "position": position_effect, "residual": residual}
            rows.append(item)
            for key in totals:
                totals[key] += item["total_pnl" if key == "total" else key]
        return self._report("PNL_EXPLAIN", {
            "start_date": previous.as_of_date.isoformat(),
            "end_date": self.snapshot.as_of_date.isoformat(),
            "totals": totals,
            "positions": sorted(rows, key=lambda item: abs(item["total_pnl"]), reverse=True),
        })

    def _report(self, analytic: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "analytic": analytic,
            "engine": self.engine_name,
            "library": "FinancePy",
            "fund_id": self.snapshot.fund_id,
            "as_of_date": self.snapshot.as_of_date.isoformat(),
            "reporting_currency": self.snapshot.reporting_currency,
            "net_asset": self.snapshot.net_asset,
            "data_quality": self.snapshot.data_quality,
            "assumptions": [
                "Fixed-income repricing uses FinancePy FlatDiscountCurve cash-flow discounting with legacy DiscountCurveFlat compatibility.",
                "Existing ARISK portfolio and market data are authoritative inputs.",
                "Results are risk estimates, not accounting valuations or regulatory capital approval.",
            ],
            **payload,
        }
