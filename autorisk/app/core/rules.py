from __future__ import annotations

import json
from pathlib import Path

from ..schemas import RiskIndicators, RuleDefinition, RuleDirection, RuleViolation, Severity


class RuleEngine:
    """Config-driven deterministic risk rule engine for enforceable guardrails."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.version = "unknown"
        self.rules: list[RuleDefinition] = []
        self.reload()

    def reload(self) -> None:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.version = str(payload.get("version", "unknown"))
        self.rules = [
            RuleDefinition.model_validate(item)
            for item in payload.get("rules", [])
            if item.get("enabled", True)
        ]
        if not self.rules:
            raise ValueError("No enabled risk rules found")

    def evaluate(self, indicators: RiskIndicators) -> tuple[Severity, list[RuleViolation]]:
        violations: list[RuleViolation] = []
        values = indicators.model_dump()

        for rule in self.rules:
            raw_value = values.get(rule.metric)
            if raw_value is None:
                continue
            actual = float(raw_value)
            severity, threshold, action = self._classify(rule, actual)
            if severity == Severity.GREEN:
                continue

            operator = ">=" if rule.direction == RuleDirection.HIGH_IS_RISK else "<="
            violations.append(
                RuleViolation(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    severity=severity,
                    description=f"{rule.name}：{actual:.4f} {operator} {threshold:.4f}",
                    threshold=threshold,
                    actual=actual,
                    action=action,
                    regulatory_ref=rule.regulatory_ref,
                )
            )

        if any(item.severity == Severity.RED for item in violations):
            return Severity.RED, violations
        if any(item.severity == Severity.YELLOW for item in violations):
            return Severity.YELLOW, violations
        return Severity.GREEN, violations

    @staticmethod
    def _classify(
        rule: RuleDefinition,
        actual: float,
    ) -> tuple[Severity, float, str]:
        if rule.direction == RuleDirection.HIGH_IS_RISK:
            if actual >= rule.red_threshold:
                return Severity.RED, rule.red_threshold, rule.red_action
            if actual >= rule.yellow_threshold:
                return Severity.YELLOW, rule.yellow_threshold, rule.yellow_action
        else:
            if actual <= rule.red_threshold:
                return Severity.RED, rule.red_threshold, rule.red_action
            if actual <= rule.yellow_threshold:
                return Severity.YELLOW, rule.yellow_threshold, rule.yellow_action
        return Severity.GREEN, 0.0, "ALLOW"

    def describe(self) -> dict:
        return {
            "version": self.version,
            "count": len(self.rules),
            "rules": [rule.model_dump(mode="json") for rule in self.rules],
        }
