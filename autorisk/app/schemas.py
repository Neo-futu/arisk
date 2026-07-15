from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TriggerSource(str, Enum):
    PRE_TRADE = "PRE_TRADE"
    POST_TRADE = "POST_TRADE"
    EOD = "EOD"
    PERIODIC = "PERIODIC"
    EVENT = "EVENT"


class Severity(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class WorkflowMode(str, Enum):
    FULL_AI = "FULL_AI"
    HYBRID = "HYBRID"


class ReportStatus(str, Enum):
    DRAFT_CREATED = "DRAFT_CREATED"
    AI_FIRST_REVIEW = "AI_FIRST_REVIEW"
    AI_SECOND_REVIEW = "AI_SECOND_REVIEW"
    WAITING_FIRST_SIGN = "WAITING_FIRST_SIGN"
    WAITING_SECOND_SIGN = "WAITING_SECOND_SIGN"
    WAITING_REVIEW_APPROVAL = "WAITING_REVIEW_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"
    EXPIRED = "EXPIRED"


class AIRecommendation(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"


class ExecutionDecision(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    BLOCK = "BLOCK"
    PENDING = "PENDING"


class SignerRole(str, Enum):
    RISK_OFFICER = "RISK_OFFICER"
    MIC = "MIC"
    AI_RISK_OFFICER = "AI_RISK_OFFICER"
    AI_MIC = "AI_MIC"
    REVIEWER = "REVIEWER"


class RuleDirection(str, Enum):
    HIGH_IS_RISK = "HIGH_IS_RISK"
    LOW_IS_RISK = "LOW_IS_RISK"


class RiskIndicators(BaseModel):
    leverage_ratio: float = Field(default=0.0, ge=0)
    single_stock_concentration: float = Field(default=0.0, ge=0)
    var_95_1d: float = Field(default=0.0, ge=0)
    liquidity_ratio: float = Field(default=1.0, ge=0)
    ytd_return: float | None = None
    max_drawdown: float | None = Field(default=None, ge=0)
    annualized_volatility: float | None = Field(default=None, ge=0)
    daily_liquid_pct: float | None = Field(default=None, ge=0)
    weekly_liquid_pct: float | None = Field(default=None, ge=0)
    nav_hkd: float | None = Field(default=None, ge=0)


class RuleDefinition(BaseModel):
    rule_id: str
    name: str
    metric: str
    direction: RuleDirection
    yellow_threshold: float
    red_threshold: float
    yellow_action: str = "WARN_AND_SIGNOFF"
    red_action: str = "BLOCK"
    regulatory_ref: str = ""
    enabled: bool = True


class RuleViolation(BaseModel):
    rule_id: str
    rule_name: str = ""
    severity: Severity
    description: str
    threshold: float | None = None
    actual: float | None = None
    action: str = ""
    regulatory_ref: str = ""


class AIReviewResult(BaseModel):
    stage: str
    reviewer_id: str
    recommendation: AIRecommendation
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    concerns: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=utc_now)
    provider: str = "deterministic-policy"


class SignRecord(BaseModel):
    signer_id: str
    signer_role: SignerRole
    decision: AIRecommendation
    signed_at: datetime = Field(default_factory=utc_now)
    notes: str = ""
    report_hash: str
    signature: str


class ReportArtifact(BaseModel):
    format: str
    path: str
    sha256: str


class RiskEvalReport(BaseModel):
    report_id: str
    request_id: str
    version: int = 1
    rule_version: str
    workflow_mode: WorkflowMode
    trigger_source: TriggerSource
    fund_code: str
    fund_name: str
    evaluation_time: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    risk_indicators: RiskIndicators
    rule_violations: list[RuleViolation] = Field(default_factory=list)
    severity: Severity = Severity.GREEN
    status: ReportStatus = ReportStatus.DRAFT_CREATED
    execution_decision: ExecutionDecision = ExecutionDecision.PENDING
    auto_commentary: str = ""
    ai_recommendation: AIRecommendation = AIRecommendation.APPROVE
    ai_confidence: float = Field(default=1.0, ge=0, le=1)
    ai_reviews: list[AIReviewResult] = Field(default_factory=list)
    requires_dual_sign: bool = True
    requires_review_ticket: bool = False
    review_ticket_id: str | None = None
    review_ticket_status: str | None = None
    first_sign: SignRecord | None = None
    second_sign: SignRecord | None = None
    rejected_by: str | None = None
    rejected_reason: str | None = None
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    proposed_trade: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = "autorisk"
    final_commentary: str | None = None
    content_hash: str = ""
    artifacts: list[ReportArtifact] = Field(default_factory=list)


class AssessRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger_source: TriggerSource
    fund_code: str = Field(min_length=1)
    fund_name: str = ""
    indicators: RiskIndicators
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    proposed_trade: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    callback_url: HttpUrl | None = None


class DemoAssessRequest(BaseModel):
    fund_name: str = Field(min_length=1, max_length=120)
    evaluation_date: date
    add_amount_hkd: float = Field(gt=0, le=10_000_000_000)


class SignRequest(BaseModel):
    signer_id: str
    signer_role: SignerRole
    decision: AIRecommendation = AIRecommendation.APPROVE
    notes: str = ""


class RejectRequest(BaseModel):
    signer_id: str
    reason: str = Field(min_length=1)


class RiskEvalListResponse(BaseModel):
    count: int
    reports: list[RiskEvalReport]


class AuditEvent(BaseModel):
    sequence: int
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    report_id: str
    actor: str
    event_time: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str = ""
    event_hash: str = ""
