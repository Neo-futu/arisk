from __future__ import annotations

from .ai_review import AIReviewEngine
from .crypto import create_signature
from ..config import settings
from ..schemas import (
    AIRecommendation,
    ExecutionDecision,
    ReportStatus,
    RiskEvalReport,
    Severity,
    SignerRole,
    WorkflowMode,
    utc_now,
)


async def apply_workflow_policy(
    report: RiskEvalReport,
    reviewer: AIReviewEngine,
) -> RiskEvalReport:
    """Apply dual-stage risk review while deterministic rules remain the hard guardrail."""
    if not settings.ai_review_enabled:
        report.status = ReportStatus.WAITING_FIRST_SIGN
        report.execution_decision = ExecutionDecision.PENDING
        report.final_commentary = "AI 審核已停用，等待人工雙簽。"
        report.updated_at = utc_now()
        return report

    report.status = ReportStatus.AI_FIRST_REVIEW
    first_review = await reviewer.review(
        report,
        stage="AI_FIRST_REVIEW",
        reviewer_id=settings.default_signers["first"],
    )
    report.ai_reviews.append(first_review)
    report.first_sign = create_signature(
        report,
        signer_id=settings.default_signers["first"],
        signer_role=SignerRole.AI_RISK_OFFICER,
        decision=first_review.recommendation,
        notes=first_review.reasoning,
        secret=settings.signing_secret,
    )

    report.status = ReportStatus.AI_SECOND_REVIEW
    second_review = await reviewer.review(
        report,
        stage="AI_SECOND_REVIEW",
        reviewer_id=settings.default_signers["second"],
    )
    report.ai_reviews.append(second_review)
    report.second_sign = create_signature(
        report,
        signer_id=settings.default_signers["second"],
        signer_role=SignerRole.AI_MIC,
        decision=second_review.recommendation,
        notes=second_review.reasoning,
        secret=settings.signing_secret,
    )

    report.ai_recommendation = second_review.recommendation
    report.ai_confidence = min(first_review.confidence, second_review.confidence)
    agreement = first_review.recommendation == second_review.recommendation

    if settings.workflow_mode == WorkflowMode.HYBRID and report.severity != Severity.GREEN:
        report.status = ReportStatus.WAITING_FIRST_SIGN
        report.execution_decision = ExecutionDecision.PENDING
        report.first_sign = None
        report.second_sign = None
        report.final_commentary = "AI 雙重覆核已完成，等待人工風控專員與 MIC 雙簽。"
    elif not agreement:
        report.status = ReportStatus.BLOCKED
        report.execution_decision = ExecutionDecision.BLOCK
        report.final_commentary = "兩級 AI 覆核結論不一致，系統按 fail-closed 原則自動阻斷。"
    elif report.severity == Severity.RED or second_review.recommendation != AIRecommendation.APPROVE:
        report.status = ReportStatus.BLOCKED
        report.execution_decision = ExecutionDecision.BLOCK
        report.final_commentary = "AI 雙簽確認紅燈或拒絕結論，交易/操作保持阻斷並完成歸檔。"
    elif report.severity == Severity.YELLOW:
        report.status = ReportStatus.APPROVED
        report.execution_decision = ExecutionDecision.ALLOW_WITH_WARNING
        report.final_commentary = "AI 雙簽批准黃燈事項，帶風險警告放行並完成歸檔。"
    else:
        report.status = ReportStatus.APPROVED
        report.execution_decision = ExecutionDecision.ALLOW
        report.final_commentary = "AI 雙簽批准綠燈事項，允許執行並完成歸檔。"

    report.updated_at = utc_now()
    return report
