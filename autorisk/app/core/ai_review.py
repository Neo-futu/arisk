from __future__ import annotations

import json
import logging

from ..config import settings
from ..schemas import AIRecommendation, AIReviewResult, RiskEvalReport, Severity

logger = logging.getLogger(__name__)


class AIReviewEngine:
    """Two-stage AI reviewer with deterministic safety guardrails and optional LLM text reasoning."""

    async def review(self, report: RiskEvalReport, *, stage: str, reviewer_id: str) -> AIReviewResult:
        recommendation, confidence, reasoning, concerns = self._deterministic_decision(report, stage)
        provider = "deterministic-policy"

        if (
            settings.ai_provider == "openai-compatible"
            and settings.llm_base_url
            and settings.llm_api_key
            and settings.llm_model
        ):
            llm_reasoning = await self._call_llm(report, stage, recommendation)
            if llm_reasoning:
                reasoning = llm_reasoning
                provider = "openai-compatible"

        return AIReviewResult(
            stage=stage,
            reviewer_id=reviewer_id,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            concerns=concerns,
            provider=provider,
        )

    @staticmethod
    def _deterministic_decision(
        report: RiskEvalReport,
        stage: str,
    ) -> tuple[AIRecommendation, float, str, list[str]]:
        concerns = [item.description for item in report.rule_violations]
        if report.severity == Severity.RED:
            return (
                AIRecommendation.REJECT,
                0.99,
                f"{stage} 覆核確認命中紅燈規則；根據先評估後執行原則，自動阻斷而非放行。",
                concerns,
            )
        if report.severity == Severity.YELLOW:
            return (
                AIRecommendation.APPROVE,
                0.92,
                f"{stage} 覆核確認僅命中黃燈預警；在保留警示及完整歸檔條件下自動批准。",
                concerns,
            )
        return (
            AIRecommendation.APPROVE,
            0.99,
            f"{stage} 覆核未發現紅黃燈規則命中，符合自動批准策略。",
            [],
        )

    async def _call_llm(
        self,
        report: RiskEvalReport,
        stage: str,
        guarded_recommendation: AIRecommendation,
    ) -> str | None:
        try:
            import httpx

            prompt = {
                "role": "基金風控審核員",
                "stage": stage,
                "rule_guardrail_decision": guarded_recommendation.value,
                "instruction": (
                    "根據結構化規則結果生成150字內繁體中文覆核理由。"
                    "不得改變 rule_guardrail_decision；紅燈必須阻斷。"
                ),
                "report": {
                    "report_id": report.report_id,
                    "fund_code": report.fund_code,
                    "severity": report.severity.value,
                    "indicators": report.risk_indicators.model_dump(mode="json"),
                    "violations": [item.model_dump(mode="json") for item in report.rule_violations],
                },
            }
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0,
                        "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                    },
                )
            response.raise_for_status()
            payload = response.json()
            return str(payload["choices"][0]["message"]["content"]).strip()[:1000]
        except Exception as exc:
            logger.warning("LLM review unavailable; deterministic fallback used: %s", exc)
            return None
