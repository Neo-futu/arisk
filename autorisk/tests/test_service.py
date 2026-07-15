import asyncio
from pathlib import Path

import pytest

from app.audit import AuditLog
from app.config import settings
from app.core.ai_review import AIReviewEngine
from app.core.artifacts import ArtifactWriter
from app.core.rules import RuleEngine
from app.schemas import (
    AIRecommendation,
    AssessRequest,
    ExecutionDecision,
    ReportStatus,
    RiskIndicators,
    SignRequest,
    SignerRole,
    TriggerSource,
    WorkflowMode,
)
from app.service import RiskEvalService, WorkflowConflict
from app.store import ReportStore


RULES = Path(__file__).resolve().parents[1] / "config" / "rules.json"


def make_service(tmp_path: Path) -> RiskEvalService:
    return RiskEvalService(
        store=ReportStore(tmp_path / "reports.json"),
        rule_engine=RuleEngine(RULES),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
        artifact_writer=ArtifactWriter(tmp_path / "artifacts"),
        ai_reviewer=AIReviewEngine(),
    )


def request(request_id: str, *, concentration: float) -> AssessRequest:
    return AssessRequest(
        request_id=request_id,
        trigger_source=TriggerSource.PRE_TRADE,
        fund_code="FUND001",
        fund_name="Test Fund",
        indicators=RiskIndicators(
            leverage_ratio=1.0,
            single_stock_concentration=concentration,
            var_95_1d=0.01,
            liquidity_ratio=0.30,
        ),
        proposed_trade={"symbol": "700.HK", "notional_hkd": 1_000_000},
    )


def test_full_ai_approves_green_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workflow_mode", WorkflowMode.FULL_AI)
    service = make_service(tmp_path)

    report = asyncio.run(service.assess(request("req-green", concentration=0.05)))
    duplicate = asyncio.run(service.assess(request("req-green", concentration=0.05)))

    assert duplicate.report_id == report.report_id
    assert report.status == ReportStatus.APPROVED
    assert report.execution_decision == ExecutionDecision.ALLOW
    assert report.first_sign is not None
    assert report.second_sign is not None
    assert report.first_sign.signature != report.second_sign.signature
    assert len(report.ai_reviews) == 2
    assert {item.format for item in report.artifacts} == {"json", "md", "html"}
    assert service.verify_audit()["valid"] is True


def test_full_ai_blocks_red(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workflow_mode", WorkflowMode.FULL_AI)
    service = make_service(tmp_path)

    report = asyncio.run(service.assess(request("req-red", concentration=0.12)))

    assert report.status == ReportStatus.BLOCKED
    assert report.execution_decision == ExecutionDecision.BLOCK
    assert report.ai_recommendation == AIRecommendation.REJECT
    assert all(item.recommendation == AIRecommendation.REJECT for item in report.ai_reviews)


def test_hybrid_requires_strict_dual_sign(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "workflow_mode", WorkflowMode.HYBRID)
    service = make_service(tmp_path)
    report = asyncio.run(service.assess(request("req-yellow", concentration=0.09)))
    assert report.status == ReportStatus.WAITING_FIRST_SIGN

    with pytest.raises(WorkflowConflict):
        asyncio.run(
            service.second_sign(
                report.report_id,
                SignRequest(signer_id="mic", signer_role=SignerRole.MIC),
            )
        )

    report = asyncio.run(
        service.first_sign(
            report.report_id,
            SignRequest(signer_id="officer", signer_role=SignerRole.RISK_OFFICER),
        )
    )
    assert report is not None and report.status == ReportStatus.WAITING_SECOND_SIGN

    report = asyncio.run(
        service.second_sign(
            report.report_id,
            SignRequest(signer_id="mic", signer_role=SignerRole.MIC, notes="reviewed"),
        )
    )
    assert report is not None and report.status == ReportStatus.APPROVED
    assert report.execution_decision == ExecutionDecision.ALLOW_WITH_WARNING
