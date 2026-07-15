from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from .audit import AuditLog
from .config import settings
from .core.ai_review import AIReviewEngine
from .core.artifacts import ArtifactWriter
from .core.crypto import canonical_json, create_signature, report_content_hash, sha256_payload, verify_signature
from .core.reporting import build_commentary, recommend_ai_action
from .core.rules import RuleEngine
from .core.workflow import apply_workflow_policy
from .schemas import (
    AIRecommendation,
    AssessRequest,
    ExecutionDecision,
    RejectRequest,
    ReportStatus,
    RiskEvalReport,
    Severity,
    SignRequest,
    SignerRole,
    utc_now,
)
from .store import ReportStore


class WorkflowConflict(ValueError):
    pass


class RiskEvalService:
    def __init__(
        self,
        *,
        store: ReportStore,
        rule_engine: RuleEngine,
        audit_log: AuditLog,
        artifact_writer: ArtifactWriter,
        ai_reviewer: AIReviewEngine,
    ):
        self.store = store
        self.rule_engine = rule_engine
        self.audit_log = audit_log
        self.artifact_writer = artifact_writer
        self.ai_reviewer = ai_reviewer

    @classmethod
    def default(cls) -> "RiskEvalService":
        return cls(
            store=ReportStore(settings.storage_path),
            rule_engine=RuleEngine(settings.rules_path),
            audit_log=AuditLog(settings.audit_path),
            artifact_writer=ArtifactWriter(settings.artifact_dir),
            ai_reviewer=AIReviewEngine(),
        )

    def _next_report_id(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"RC-{today}-{uuid.uuid4().hex[:8].upper()}"

    async def assess(self, req: AssessRequest) -> RiskEvalReport:
        existing = self.store.find_by_request_id(req.request_id)
        if existing:
            return existing

        severity, violations = self.rule_engine.evaluate(req.indicators)
        ai_recommendation, ai_confidence = recommend_ai_action(severity, violations)
        report = RiskEvalReport(
            report_id=self._next_report_id(),
            request_id=req.request_id,
            rule_version=self.rule_engine.version,
            workflow_mode=settings.workflow_mode,
            trigger_source=req.trigger_source,
            fund_code=req.fund_code,
            fund_name=req.fund_name or req.fund_code,
            risk_indicators=req.indicators,
            rule_violations=violations,
            severity=severity,
            status=ReportStatus.DRAFT_CREATED,
            execution_decision=ExecutionDecision.PENDING,
            auto_commentary=build_commentary(req, severity, violations),
            ai_recommendation=ai_recommendation,
            ai_confidence=ai_confidence,
            requires_dual_sign=True,
            requires_review_ticket=settings.workflow_mode.value == "HYBRID" and severity == Severity.RED,
            market_snapshot=req.market_snapshot,
            proposed_trade=req.proposed_trade,
            metadata=req.metadata,
            final_commentary="結構化風控評估草案已生成。",
        )
        report.content_hash = report_content_hash(report)
        self.store.upsert(report)
        self.audit_log.append(
            event_type="DRAFT_CREATED",
            report_id=report.report_id,
            actor="autorisk-rule-engine",
            details={
                "request_id": report.request_id,
                "severity": report.severity.value,
                "rule_version": report.rule_version,
                "violations": len(report.rule_violations),
            },
        )

        report = await apply_workflow_policy(report, self.ai_reviewer)
        for review in report.ai_reviews:
            self.audit_log.append(
                event_type=review.stage,
                report_id=report.report_id,
                actor=review.reviewer_id,
                details={
                    "recommendation": review.recommendation.value,
                    "confidence": review.confidence,
                    "provider": review.provider,
                },
            )
        report = self._persist_final(report, actor="autorisk-workflow")
        await self._send_callback(str(req.callback_url) if req.callback_url else None, report)
        return report

    async def get(self, report_id: str) -> RiskEvalReport | None:
        return self.store.get(report_id)

    def list(
        self,
        *,
        status: str | None = None,
        fund_code: str | None = None,
        limit: int = 50,
    ) -> list[RiskEvalReport]:
        return self.store.list(status=status, fund_code=fund_code, limit=limit)

    def rules(self) -> dict:
        return self.rule_engine.describe()

    def reload_rules(self) -> dict:
        self.rule_engine.reload()
        return self.rule_engine.describe()

    async def first_sign(self, report_id: str, body: SignRequest) -> RiskEvalReport | None:
        report = self.store.get(report_id)
        if not report:
            return None
        if report.status != ReportStatus.WAITING_FIRST_SIGN:
            raise WorkflowConflict(f"First sign is not allowed from status {report.status.value}")
        if body.signer_role not in {SignerRole.RISK_OFFICER, SignerRole.REVIEWER}:
            raise WorkflowConflict("First signer must be RISK_OFFICER or REVIEWER")

        report.first_sign = create_signature(
            report,
            signer_id=body.signer_id,
            signer_role=body.signer_role,
            decision=body.decision,
            notes=body.notes,
            secret=settings.signing_secret,
        )
        if body.decision != AIRecommendation.APPROVE:
            report.status = ReportStatus.REJECTED
            report.execution_decision = ExecutionDecision.BLOCK
            report.rejected_by = body.signer_id
            report.rejected_reason = body.notes or body.decision.value
            report.final_commentary = "人工初審拒絕，操作保持阻斷。"
        else:
            report.status = ReportStatus.WAITING_SECOND_SIGN
            report.final_commentary = "人工初審通過，等待 MIC 終審。"
        return self._persist_final(report, actor=body.signer_id, event_type="FIRST_SIGNED")

    async def second_sign(self, report_id: str, body: SignRequest) -> RiskEvalReport | None:
        report = self.store.get(report_id)
        if not report:
            return None
        if report.status != ReportStatus.WAITING_SECOND_SIGN or report.first_sign is None:
            raise WorkflowConflict("Second sign requires a completed first sign")
        if body.signer_role != SignerRole.MIC:
            raise WorkflowConflict("Second signer must be MIC")
        if body.signer_id == report.first_sign.signer_id:
            raise WorkflowConflict("Dual signers must be different identities")
        if report.severity == Severity.RED and body.decision == AIRecommendation.APPROVE and not body.notes.strip():
            raise WorkflowConflict("Approving a RED report requires an explicit override reason")

        report.second_sign = create_signature(
            report,
            signer_id=body.signer_id,
            signer_role=body.signer_role,
            decision=body.decision,
            notes=body.notes,
            secret=settings.signing_secret,
        )
        if body.decision == AIRecommendation.APPROVE:
            report.status = ReportStatus.APPROVED
            report.execution_decision = (
                ExecutionDecision.ALLOW_WITH_WARNING
                if report.severity != Severity.GREEN
                else ExecutionDecision.ALLOW
            )
            report.final_commentary = "人工雙簽完成，最終批准。"
        else:
            report.status = ReportStatus.REJECTED
            report.execution_decision = ExecutionDecision.BLOCK
            report.rejected_by = body.signer_id
            report.rejected_reason = body.notes or body.decision.value
            report.final_commentary = "MIC 終審拒絕，操作保持阻斷。"
        return self._persist_final(report, actor=body.signer_id, event_type="SECOND_SIGNED")

    def reject(self, report_id: str, body: RejectRequest) -> RiskEvalReport | None:
        report = self.store.get(report_id)
        if not report:
            return None
        if report.status in {ReportStatus.APPROVED, ReportStatus.BLOCKED, ReportStatus.REJECTED, ReportStatus.ARCHIVED}:
            raise WorkflowConflict(f"Terminal report cannot be rejected from status {report.status.value}")
        report.status = ReportStatus.REJECTED
        report.execution_decision = ExecutionDecision.BLOCK
        report.rejected_by = body.signer_id
        report.rejected_reason = body.reason
        report.final_commentary = "已拒絕並保留完整審計記錄。"
        return self._persist_final(report, actor=body.signer_id, event_type="REJECTED")

    def list_audit(self, report_id: str | None = None, limit: int = 200):
        return self.audit_log.list(report_id=report_id, limit=limit)

    def verify_audit(self) -> dict:
        return self.audit_log.verify()

    def verify_report(self, report_id: str) -> dict | None:
        report = self.store.get(report_id)
        if not report:
            return None
        artifact_checks = []
        for artifact in report.artifacts:
            path = settings.artifact_dir / artifact.path
            actual = sha256_payload(path.read_text(encoding="utf-8")) if path.is_file() else ""
            artifact_checks.append(
                {
                    "path": artifact.path,
                    "valid": bool(actual) and actual == artifact.sha256,
                }
            )
        signature_checks = {
            "first_sign": bool(report.first_sign)
            and verify_signature(report.report_id, report.first_sign, settings.signing_secret),
            "second_sign": bool(report.second_sign)
            and verify_signature(report.report_id, report.second_sign, settings.signing_secret),
        }
        return {
            "report_id": report.report_id,
            "content_hash_valid": report.content_hash == report_content_hash(report),
            "signatures": signature_checks,
            "artifacts": artifact_checks,
            "audit_chain": self.verify_audit(),
        }

    def resolve_artifact(self, report_id: str, filename: str) -> Path:
        base = (settings.artifact_dir / report_id).resolve()
        path = (base / filename).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise FileNotFoundError(filename) from exc
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path

    def _persist_final(
        self,
        report: RiskEvalReport,
        *,
        actor: str,
        event_type: str | None = None,
    ) -> RiskEvalReport:
        report.updated_at = utc_now()
        report.content_hash = report_content_hash(report)
        report.artifacts = self.artifact_writer.write(report)
        self.store.upsert(report)
        self.audit_log.append(
            event_type=event_type or report.status.value,
            report_id=report.report_id,
            actor=actor,
            details={
                "status": report.status.value,
                "execution_decision": report.execution_decision.value,
                "content_hash": report.content_hash,
                "artifact_count": len(report.artifacts),
            },
        )
        return report

    async def _send_callback(self, callback_url: str | None, report: RiskEvalReport) -> None:
        if not callback_url:
            return
        if not settings.callback_enabled:
            self.audit_log.append(
                event_type="CALLBACK_SKIPPED",
                report_id=report.report_id,
                actor="autorisk-callback",
                details={"reason": "AUTORISK_CALLBACK_ENABLED=false"},
            )
            return
        try:
            import hashlib
            import hmac
            import httpx

            payload = report.model_dump(mode="json")
            body = canonical_json(payload)
            signature = hmac.new(
                settings.signing_secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    callback_url,
                    content=body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-AutoRisk-Signature": signature,
                        "X-AutoRisk-Event": "risk-evaluation.completed",
                    },
                )
            response.raise_for_status()
            self.audit_log.append(
                event_type="CALLBACK_DELIVERED",
                report_id=report.report_id,
                actor="autorisk-callback",
                details={"status_code": response.status_code},
            )
        except Exception as exc:
            self.audit_log.append(
                event_type="CALLBACK_FAILED",
                report_id=report.report_id,
                actor="autorisk-callback",
                details={"error": str(exc)[:300]},
            )
