import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_rule_engine_accepts_configured_dynamic_numeric_metric(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "version": "dynamic-1",
                "rules": [
                    {
                        "rule_id": "LIMIT_DURATION",
                        "name": "久期限制",
                        "metric": "duration_years",
                        "direction": "HIGH_IS_RISK",
                        "yellow_threshold": 2.0,
                        "red_threshold": 3.0,
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    engine = RuleEngine(rules_path)

    severity, violations = engine.evaluate(RiskIndicators(duration_years=2.5))

    assert severity == Severity.YELLOW
    assert violations[0].rule_id == "LIMIT_DURATION"

    with pytest.raises(ValidationError):
        RiskIndicators(duration_years="not-a-number")
