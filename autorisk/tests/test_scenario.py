from datetime import date

from app.core.scenario import DemoScenarioCalculator
from app.schemas import DemoAssessRequest


def test_demo_calculation_is_reproducible_and_post_trade() -> None:
    calculator = DemoScenarioCalculator()
    request = DemoAssessRequest(
        fund_name="Scenario Fund",
        evaluation_date=date(2026, 7, 15),
        add_amount_hkd=10_000_000,
    )

    first, first_calculation = calculator.calculate(request)
    second, second_calculation = calculator.calculate(request)

    assert first.fund_code == second.fund_code
    assert first.indicators == second.indicators
    assert first_calculation["nav_history"] == second_calculation["nav_history"]
    assert first.request_id != second.request_id
    assert first.indicators.ytd_return is not None
    assert first.indicators.max_drawdown is not None
    assert first.indicators.annualized_volatility is not None
    assert first.market_snapshot["post_trade_target_holding_hkd"] > first.market_snapshot["current_target_holding_hkd"]


def test_larger_addition_increases_concentration_and_reduces_liquidity() -> None:
    calculator = DemoScenarioCalculator()
    small, _ = calculator.calculate(
        DemoAssessRequest(
            fund_name="Scenario Fund",
            evaluation_date=date(2026, 7, 15),
            add_amount_hkd=5_000_000,
        )
    )
    large, _ = calculator.calculate(
        DemoAssessRequest(
            fund_name="Scenario Fund",
            evaluation_date=date(2026, 7, 15),
            add_amount_hkd=50_000_000,
        )
    )

    assert large.indicators.single_stock_concentration > small.indicators.single_stock_concentration
    assert large.indicators.leverage_ratio > small.indicators.leverage_ratio
    assert large.indicators.liquidity_ratio < small.indicators.liquidity_ratio