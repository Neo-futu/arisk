"""審核 API Router — 審核員操作界面：認領、批准、拒絕、查詢。"""
from __future__ import annotations

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, get_redis, verify_api_key
from ...review.review_manager import (
    approve_review,
    claim_review,
    create_review_request,
    get_pending_reviews,
    get_review_detail,
    reject_review,
)
from ...review.checkpoint import notify_decision
from ...review.checkpoint import requires_review

router = APIRouter(dependencies=[Depends(verify_api_key)])


# ─── Request / Response Models ───────────────────────────────────

class CreateReviewRequest(BaseModel):
    category: str
    title: str
    summary: str
    triggered_by: str
    payload: dict = {}
    fund_id: str | None = None
    as_of_date: str | None = None
    task_id: str | None = None
    artefact_path: str | None = None
    artefact_url: str | None = None


class ApproveRequest(BaseModel):
    reviewer: str
    notes: str = ""
    override_reason: str = ""   # 如違規仍存在，需填寫覆蓋原因


class RejectRequest(BaseModel):
    reviewer: str
    reason: str                 # 必填


class ClaimRequest(BaseModel):
    reviewer: str


class SkillExtractionGateRequest(BaseModel):
    """審批 gate：專家知識/技能提取前先經過人工或小富 AI 審核。"""
    channel: str = "agentchat"
    skill_name: str | None = None
    query: str | None = None
    triggered_by: str = "aiagent.execute_tool"
    session_id: str | None = None
    user_id: str | None = None
    payload: dict = {}


# ─── Endpoints ───────────────────────────────────────────────────

@router.post("/request", status_code=201)
async def submit_review_request(
    body: CreateReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    提交人工審核請求。由 agent / Processing 代碼調用。
    返回 review_id 供後續輪詢。
    """
    review_id = await create_review_request(
        db,
        category=body.category,
        title=body.title,
        summary=body.summary,
        triggered_by=body.triggered_by,
        payload=body.payload,
        fund_id=body.fund_id,
        as_of_date=body.as_of_date,
        task_id=body.task_id,
        artefact_path=body.artefact_path,
        artefact_url=body.artefact_url,
    )
    return {"review_id": review_id, "status": "PENDING"}


@router.get("/pending")
async def list_pending_reviews(
    fund_id: str | None = None,
    category: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    取待審核列表。審核員在 Web UI 或 CLI 查詢此接口。
    按優先級（緊急在前）+ 時間（舊在前）排序。
    """
    reviews = await get_pending_reviews(db, fund_id=fund_id, category=category, limit=limit)
    return {"count": len(reviews), "reviews": reviews}


@router.post("/gates/skill-extraction")
@requires_review(
    category="AGENT_HANDOFF",
    title="專家/Agent Chat 技能提取審批",
    summary="敏感技能提取請求，需人工或小富 AI 建議後放行",
    fund_id_param="fund_id",
    timeout_seconds=900,
)
async def gate_skill_extraction(
    body: SkillExtractionGateRequest,
    fund_id: str | None = Query(default=None),
    as_of_date: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    讓專家知識提取與 Agent Chat 技能提取走統一審批門禁。

    行為說明：
    1. 進入端點即由 requires_review 建立 review_request + checkpoint 並阻塞
    2. 審核員在 /review-ui/inbox 批准/拒絕，或採納小富 AI 建議
    3. 批准後端點返回 200；拒絕時 requires_review 直接拋出 403
    """
    return {
        "approved": True,
        "category": "AGENT_HANDOFF",
        "channel": body.channel,
        "skill_name": body.skill_name,
        "query": body.query,
        "fund_id": fund_id,
        "as_of_date": as_of_date,
        "triggered_by": body.triggered_by,
        "session_id": body.session_id,
        "user_id": body.user_id,
        "payload": body.payload,
        "message": "審批已通過，允許技能提取。",
    }


@router.get("/{review_id}")
async def get_review(review_id: str, db: AsyncSession = Depends(get_db)):
    """取審核詳情，包含 payload、artefact 鏈接、決策歷史、checkpoint 狀態。"""
    detail = await get_review_detail(db, review_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Review not found")
    return detail


@router.post("/{review_id}/claim")
async def claim(
    review_id: str,
    body: ClaimRequest,
    db: AsyncSession = Depends(get_db),
):
    """審核員認領請求（將狀態改為 IN_REVIEW，防止多人重複審核）。"""
    ok = await claim_review(db, review_id, body.reviewer)
    if not ok:
        raise HTTPException(status_code=409, detail="Already claimed or not in PENDING state")
    return {"review_id": review_id, "status": "IN_REVIEW", "assigned_to": body.reviewer}


@router.post("/{review_id}/approve")
async def approve(
    review_id: str,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    批准審核請求。

    關鍵流程：
    1. 更新 DB 狀態為 APPROVED
    2. 寫審計日誌
    3. 通過 Redis pub/sub 解鎖等待的 agent checkpoint
    """
    ok = await approve_review(
        db, review_id, body.reviewer,
        notes=body.notes,
        override_reason=body.override_reason,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="Review not in approvable state")

    # 通知等待的 agent
    await notify_decision(redis, review_id, "APPROVED")
    return {"review_id": review_id, "status": "APPROVED", "reviewer": body.reviewer}


@router.post("/{review_id}/reject")
async def reject(
    review_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    拒絕審核請求。

    拒絕後 agent checkpoint 收到通知，中止被保護的操作。
    reason 必填——是審計記錄的重要依據。
    """
    ok = await reject_review(db, review_id, body.reviewer, body.reason)
    if not ok:
        raise HTTPException(status_code=409, detail="Review not in rejectable state")

    # 通知等待的 agent
    await notify_decision(redis, review_id, "REJECTED")
    return {"review_id": review_id, "status": "REJECTED", "reviewer": body.reviewer}


@router.get("/{review_id}/ai-review")
async def get_ai_review(review_id: str, db: AsyncSession = Depends(get_db)):
    """
    取小富 AI 審核結果。
    如 AI 審核尚未完成，返回 status=pending。
    """
    from sqlalchemy import text
    row = await db.execute(
        text("""
            SELECT ai_reviewer, ai_review_at, ai_recommendation, ai_risk_level,
                   ai_review_result, ai_auto_approved, status
            FROM fsi.review_requests WHERE review_id = :rid
        """),
        {"rid": review_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")

    if r.ai_review_at is None:
        return {"review_id": review_id, "ai_status": "pending", "message": "小富正在分析中..."}

    return {
        "review_id": review_id,
        "ai_status": "completed",
        "ai_reviewer": r.ai_reviewer,
        "ai_review_at": r.ai_review_at,
        "ai_recommendation": r.ai_recommendation,
        "ai_risk_level": r.ai_risk_level,
        "ai_result": r.ai_review_result,
        "ai_auto_approved": r.ai_auto_approved,
    }


@router.post("/{review_id}/ai-approve")
async def ai_auto_approve(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    接受小富的自動批准建議（auto_approvable=True 時可用）。
    記錄為「採納小富建議」，仍屬系統操作，審計日誌標明 actor=小富(AI)。
    COMPLIANCE_BREACH / HIGH_RISK 類別禁止此操作。
    """
    from sqlalchemy import text
    row = await db.execute(
        text("""
            SELECT category, status, ai_recommendation, ai_auto_approved, ai_risk_level
            FROM fsi.review_requests WHERE review_id = :rid
        """),
        {"rid": review_id},
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    if r.category in ("COMPLIANCE_BREACH", "HIGH_RISK"):
        raise HTTPException(status_code=403, detail="此類別禁止 AI 自動批准，必須人工審核")
    if r.ai_recommendation != "APPROVE":
        raise HTTPException(status_code=409, detail=f"小富建議為 {r.ai_recommendation}，不可自動批准")
    if r.status not in ("PENDING", "IN_REVIEW"):
        raise HTTPException(status_code=409, detail=f"審核已處於 {r.status} 狀態")

    # 以「小富(AI)」身份批准
    ok = await approve_review(
        db, review_id,
        reviewer="小富(AI)",
        notes=f"採納小富 AI 自動批准建議（風險等級：{r.ai_risk_level}）",
        override_reason="",
    )
    await db.execute(
        text("UPDATE fsi.review_requests SET ai_auto_approved = TRUE WHERE review_id = :rid"),
        {"rid": review_id},
    )
    await db.commit()
    await notify_decision(redis, review_id, "APPROVED")
    return {"review_id": review_id, "status": "APPROVED", "reviewer": "小富(AI)", "auto": True}


@router.get("/history/audit-log")
async def get_audit_log(
    fund_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    不可篡改審計日誌查詢。合規存檔用。
    """
    from sqlalchemy import text
    sql = "SELECT * FROM fsi.audit_log"
    params: dict = {}
    if fund_id:
        sql += " WHERE fund_id = :fund_id"
        params["fund_id"] = fund_id
    sql += " ORDER BY event_time DESC LIMIT :limit"
    params["limit"] = limit

    rows = await db.execute(text(sql), params)
    logs = [dict(r._mapping) for r in rows]
    return {"count": len(logs), "audit_log": logs}
