from __future__ import annotations

from datetime import timedelta

from .crypto import sha256_payload
from ..schemas import (
    AssessmentConclusion,
    ConclusionCode,
    ConclusionDirective,
    ConclusionFeedbackContract,
    ConclusionVerification,
    DirectiveAction,
    ExecutionDecision,
    FeedbackStatus,
    RiskEvalReport,
)


def _build_directive(report: RiskEvalReport) -> ConclusionDirective:
    restrictions = [
        f"[{item.severity.value}] {item.rule_name or item.rule_id}：{item.description}；處置：{item.action}"
        for item in report.rule_violations
    ]

    if report.execution_decision == ExecutionDecision.ALLOW:
        return ConclusionDirective(
            conclusion_code=ConclusionCode.APPROVED,
            action=DirectiveAction.PROCEED,
            headline="准予執行",
            summary="本次請求已通過規則引擎及兩級 AI 覆核，可按申報內容執行。",
            instructions=[
                "執行前核對請求編號、基金及報告內容哈希。",
                "如交易條件、持倉、市場快照或風險指標發生變化，必須重新提交審核。",
                "執行系統完成處置後，應向 feedback 接口回傳處理回執。",
            ],
            restrictions=restrictions,
        )

    if report.execution_decision == ExecutionDecision.ALLOW_WITH_WARNING:
        return ConclusionDirective(
            conclusion_code=ConclusionCode.APPROVED_WITH_CONDITIONS,
            action=DirectiveAction.PROCEED_WITH_CONTROLS,
            headline="附條件准予執行",
            summary="本次請求命中預警規則，僅可在落實全部控制措施後執行。",
            instructions=[
                "執行前逐項落實本結論單列示的預警處置要求。",
                "執行前核對請求編號、基金及報告內容哈希。",
                "任何輸入或市場條件變化均需以新 request_id 重新審核。",
                "執行系統完成處置後，應向 feedback 接口回傳處理回執。",
            ],
            restrictions=restrictions,
        )

    return ConclusionDirective(
        conclusion_code=ConclusionCode.NOT_APPROVED,
        action=DirectiveAction.DO_NOT_PROCEED,
        headline="禁止執行",
        summary="本次請求未獲風控批准，執行系統必須保持阻斷。",
        instructions=[
            "不得執行、拆分執行或繞過本次阻斷結論。",
            "修正紅線或拒絕原因後，必須使用新的 request_id 重新提交審核。",
            "執行系統確認阻斷後，應向 feedback 接口回傳 OK 回執。",
        ],
        restrictions=restrictions or [report.final_commentary or "風控結論為阻斷。"],
    )


def build_assessment_conclusion(
    report: RiskEvalReport,
    *,
    validity_minutes: int,
) -> AssessmentConclusion:
    """Build a stable, machine-readable final-decision certificate from a report."""
    report_id = report.report_id
    conclusion = AssessmentConclusion(
        certificate_id=f"ARC-{report_id}",
        report_id=report_id,
        request_id=report.request_id,
        issued_at=report.updated_at,
        valid_until=report.updated_at + timedelta(minutes=validity_minutes),
        validity_note=(
            "本結論僅適用於本次 request_id、已提交的結構化指標及市場快照；"
            "任一輸入變化、超過有效期或內容哈希不一致時均須重新審核。"
        ),
        fund_code=report.fund_code,
        fund_name=report.fund_name,
        trigger_source=report.trigger_source,
        rule_version=report.rule_version,
        workflow_mode=report.workflow_mode,
        report_status=report.status,
        severity=report.severity,
        execution_decision=report.execution_decision,
        directive=_build_directive(report),
        risk_indicators=report.risk_indicators,
        rule_violations=report.rule_violations,
        ai_reviews=report.ai_reviews,
        approvals=[item for item in (report.first_sign, report.second_sign) if item is not None],
        verification=ConclusionVerification(
            report_content_hash=report.content_hash,
            verify_url=f"/api/v1/risk-evals/reports/{report_id}/verify",
        ),
        feedback=ConclusionFeedbackContract(
            endpoint=f"/api/v1/risk-evals/reports/{report_id}/feedback",
            required_fields=[
                "idempotency_key",
                "status",
                "actor_id",
                "observed_report_hash",
                "observed_decision",
            ],
            accepted_statuses=[FeedbackStatus.OK, FeedbackStatus.REJECTED, FeedbackStatus.FAILED],
        ),
    )
    payload = conclusion.model_dump(mode="json")
    payload["verification"].pop("certificate_hash", None)
    conclusion.verification.certificate_hash = sha256_payload(payload)
    return conclusion
