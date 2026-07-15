from __future__ import annotations

import hashlib
import math
import random
import statistics
from datetime import date, timedelta
from uuid import uuid4

from ..schemas import AssessRequest, DemoAssessRequest, RiskIndicators, TriggerSource


class DemoScenarioCalculator:
    """Build reproducible demonstration market data and post-trade risk metrics."""

    data_source = "AUTORISK_DEMO_SYNTHETIC_NAV"

    def calculate(self, request: DemoAssessRequest) -> tuple[AssessRequest, dict]:
        seed = int(
            hashlib.sha256(request.fund_name.strip().encode("utf-8")).hexdigest()[:16],
            16,
        )
        nav_history = self._nav_history(request.evaluation_date, seed)
        nav_values = [point["nav"] for point in nav_history]
        daily_returns = [
            nav_values[index] / nav_values[index - 1] - 1
            for index in range(1, len(nav_values))
        ]

        ytd_return = nav_values[-1] / nav_values[0] - 1
        max_drawdown = self._max_drawdown(nav_values)
        daily_volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0
        average_return = statistics.fmean(daily_returns) if daily_returns else 0.0
        var_95_1d = max(0.0, 1.645 * daily_volatility - average_return)
        annualized_volatility = daily_volatility * math.sqrt(252)

        fund_nav_hkd = float(200_000_000 + seed % 301_000_000)
        current_target_holding_hkd = fund_nav_hkd * (0.035 + (seed % 26) / 1000)
        current_gross_exposure_hkd = fund_nav_hkd * (0.82 + (seed % 13) / 100)
        available_liquidity_hkd = fund_nav_hkd * (0.24 + (seed % 9) / 100)
        post_trade_holding_hkd = current_target_holding_hkd + request.add_amount_hkd

        indicators = RiskIndicators(
            leverage_ratio=(current_gross_exposure_hkd + request.add_amount_hkd) / fund_nav_hkd,
            single_stock_concentration=post_trade_holding_hkd / fund_nav_hkd,
            var_95_1d=var_95_1d,
            liquidity_ratio=max(0.0, available_liquidity_hkd - request.add_amount_hkd)
            / fund_nav_hkd,
            ytd_return=ytd_return,
            max_drawdown=max_drawdown,
            annualized_volatility=annualized_volatility,
            nav_hkd=fund_nav_hkd,
        )
        fund_code = f"DEMO-{seed % 100000:05d}"
        request_id = (
            f"WEB-{request.evaluation_date:%Y%m%d}-{uuid4().hex[:10].upper()}"
        )
        snapshot = {
            "data_source": self.data_source,
            "evaluation_date": request.evaluation_date.isoformat(),
            "fund_nav_hkd": round(fund_nav_hkd, 2),
            "current_target_holding_hkd": round(current_target_holding_hkd, 2),
            "post_trade_target_holding_hkd": round(post_trade_holding_hkd, 2),
            "available_liquidity_before_hkd": round(available_liquidity_hkd, 2),
            "available_liquidity_after_hkd": round(
                max(0.0, available_liquidity_hkd - request.add_amount_hkd),
                2,
            ),
            "nav_history": nav_history,
        }
        assess_request = AssessRequest(
            request_id=request_id,
            trigger_source=TriggerSource.PRE_TRADE,
            fund_code=fund_code,
            fund_name=request.fund_name.strip(),
            indicators=indicators,
            proposed_trade={
                "action": "ADD_POSITION",
                "amount_hkd": request.add_amount_hkd,
                "requested_at": request.evaluation_date.isoformat(),
            },
            market_snapshot=snapshot,
            metadata={
                "scenario": "WEB_DEMO_ADD_POSITION",
                "data_source": self.data_source,
                "calculation_method": {
                    "var_95_1d": "historical daily returns, parametric 95% one-tailed VaR",
                    "ytd_return": "latest NAV / first NAV of year - 1",
                    "max_drawdown": "maximum peak-to-trough decline",
                },
            },
        )
        calculated = {
            "fund_code": fund_code,
            "request_id": request_id,
            "data_source": self.data_source,
            "portfolio": {key: value for key, value in snapshot.items() if key != "nav_history"},
            "metrics": indicators.model_dump(mode="json"),
            "nav_history": nav_history,
        }
        return assess_request, calculated

    @staticmethod
    def _nav_history(evaluation_date: date, seed: int) -> list[dict]:
        start = date(evaluation_date.year, 1, 1)
        if evaluation_date < start:
            evaluation_date = start
        days = []
        cursor = start
        while cursor <= evaluation_date:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        if len(days) < 20:
            cursor = start - timedelta(days=1)
            while len(days) < 20:
                if cursor.weekday() < 5:
                    days.insert(0, cursor)
                cursor -= timedelta(days=1)

        rng = random.Random(seed + evaluation_date.toordinal())
        drift = 0.00018 + (seed % 9) / 1_000_000
        volatility = 0.0045 + (seed % 20) / 10_000
        nav = 100.0
        result = []
        for index, day in enumerate(days):
            cycle = math.sin((index + seed % 31) / 11) * 0.0008
            shock = -volatility * 2.3 if index and index % 67 == seed % 17 else 0.0
            daily_return = max(-0.12, min(0.12, drift + cycle + rng.gauss(0, volatility) + shock))
            nav *= 1 + daily_return
            result.append({"date": day.isoformat(), "nav": round(nav, 4)})
        return result

    @staticmethod
    def _max_drawdown(nav_values: list[float]) -> float:
        peak = nav_values[0]
        max_drawdown = 0.0
        for value in nav_values:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, 1 - value / peak)
        return max_drawdown