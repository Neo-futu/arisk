from pathlib import Path

from app.core.rules import RuleEngine
from app.schemas import RiskIndicators, Severity


RULES = Path(__file__).resolve().parents[1] / "config" / "rules.json"


def test_rule_engine_green_yellow_red() -> None:
    engine = RuleEngine(RULES)

    severity, violations = engine.evaluate(
        RiskIndicators(
            leverage_ratio=1.0,
            single_stock_concentration=0.05,
            var_95_1d=0.01,
            liquidity_ratio=0.30,
        )
    )
    assert severity == Severity.GREEN
    assert violations == []

    severity, violations = engine.evaluate(
        RiskIndicators(
            leverage_ratio=1.16,
            single_stock_concentration=0.05,
            var_95_1d=0.01,
            liquidity_ratio=0.30,
        )
    )
    assert severity == Severity.YELLOW
    assert violations[0].rule_id == "LIMIT_LEVERAGE"

    severity, violations = engine.evaluate(
        RiskIndicators(
            leverage_ratio=1.0,
            single_stock_concentration=0.12,
            var_95_1d=0.01,
            liquidity_ratio=0.30,
        )
    )
    assert severity == Severity.RED
    assert violations[0].action == "BLOCK"
