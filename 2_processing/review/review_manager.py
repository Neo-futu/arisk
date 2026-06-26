"""人工審核管理器：創建審核請求、批准/拒絕、查詢狀態、寫審計日誌。

設計原則：
- 所有寫入操作必須先通過審核，特別是 COMPLIANCE_BREACH 類別
- 審計日誌 append-only，不允許修改
- 審核狀態通過 Redis pub/sub 實時推送給 Web UI
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 各類別的默認 SLA（分鐘）
SLA_MINUTES: dict[str, int] = {
    "COMPLIANCE_BREACH": 30,   # 合規違規：30 分鐘內必須處理
    "HIGH_RISK":         60,
    "REPORT_PUBLISH":    120,
    "DATA_WRITE":        60,
    "DATA_LOAD":         60,
    "AGENT_HANDOFF":     30,
    "MANUAL":            240,
}

# 各類別的默認優先級（1=緊急）
PRIORITY: dict[str, int] = {
    "COMPLIANCE_BREACH": 1,
    "HIGH_RISK":         1,
    "REPORT_PUBLISH":    2,
    "DATA_WRITE":        2,
    "DATA_LOAD":         2,
    "AGENT_HANDOFF":     2,
    "MANUAL":            3,
}


async def create_review_request(
    db: AsyncSession,
    *,
    category: str,
    title: str,
    summary: str,
    triggered_by: str,
    payload: dict,
    fund_id: str | None = None,
    as_of_date=None,
    task_id: str | None = None,
    artefact_path: str | None = None,
    artefact_url: str | None = None,
) -> str:
    """
    創建人工審核請求，返回 review_id。

    被以下場景調用：
    - exposure_engine.py：發現 WAM/WAL/集中度違規
    - report-writer subagent：報告發布前
    - load_positions.py：新持倉文件載入前
    - orchestrate.py：agent 交接前
    """
    review_id = str(uuid.uuid4())
    sla = SLA_MINUTES.get(category, 60)
    priority = PRIORITY.get(category, 2)
    expires_at = datetime.utcnow() + timedelta(minutes=sla)

    await db.execute(
        text("""
            INSERT INTO fsi.review_requests (
                review_id, category, status, triggered_by, task_id,
                fund_id, as_of_date, title, summary, payload,
                artefact_path, artefact_url, priority, sla_minutes, expires_at
            ) VALUES (
                :review_id, :category, 'PENDING', :triggered_by, :task_id,
                :fund_id, :as_of_date, :title, :summary, :payload,
                :artefact_path, :artefact_url, :priority, :sla, :expires_at
            )
        """),
        {
            "review_id": review_id,
            "category": category,
            "triggered_by": triggered_by,
            "task_id": task_id,
            "fund_id": fund_id,
            "as_of_date": as_of_date,
            "title": title,
            "summary": summary,
            "payload": json.dumps(payload),
            "artefact_path": artefact_path,
            "artefact_url": artefact_url,
            "priority": priority,
            "sla": sla,
            "expires_at": expires_at,
        },
    )

    # 記錄審計日誌
    await _write_audit(db, "REVIEW_CREATED", triggered_by, review_id=review_id,
                       fund_id=fund_id, task_id=task_id,
                       details={"category": category, "title": title, "priority": priority})
    await db.commit()

    logger.info("Review created: %s [%s] priority=%d", review_id, category, priority)

    # 自動觸發小富 AI 審核（非同步後台，不阻塞主流程）
    import asyncio
    review_data = {
        "category": category, "title": title, "summary": summary,
        "triggered_by": triggered_by, "fund_id": fund_id,
        "as_of_date": str(as_of_date) if as_of_date else None,
        "payload": payload,
    }
    asyncio.create_task(_run_ai_review_background(db, review_id, review_data))

    return review_id


async def _run_ai_review_background(
    db: AsyncSession,
    review_id: str,
    review_data: dict,
) -> None:
    """
    後台執行小富 AI 審核（不阻塞 create_review_request 的返回）。
    小富完成後更新 review_requests 的 ai_* 字段。
    """
    try:
        from .ai_reviewer import run_ai_review
        result = await run_ai_review(db, review_id, review_data)
        await _write_audit(
            db, "AI_REVIEW_COMPLETED", "小富",
            review_id=review_id, fund_id=review_data.get("fund_id"),
            details={
                "risk_level": result.risk_level,
                "recommendation": result.recommendation,
                "auto_approvable": result.auto_approvable,
            },
        )
        await db.commit()
    except Exception as e:
        logger.error("小富 AI 審核後台任務失敗 [%s]: %s", review_id, e)


async def approve_review(
    db: AsyncSession,
    review_id: str,
    reviewer: str,
    notes: str = "",
    override_reason: str = "",
) -> bool:
    """
    批准審核請求。返回是否成功（False = 請求不存在或狀態不對）。

    批准後：
    1. 更新 review_requests.status = APPROVED
    2. 插入 review_decisions 記錄
    3. 寫審計日誌
    4. 通過 Redis pub/sub 通知等待的 agent checkpoint
    """
    row = await db.execute(
        text("SELECT status, fund_id, task_id FROM fsi.review_requests WHERE review_id = :rid"),
        {"rid": review_id},
    )
    req = row.fetchone()
    if not req or req.status not in ("PENDING", "IN_REVIEW"):
        return False

    await db.execute(
        text("UPDATE fsi.review_requests SET status = 'APPROVED', updated_at = NOW() WHERE review_id = :rid"),
        {"rid": review_id},
    )
    await db.execute(
        text("""
            INSERT INTO fsi.review_decisions (review_id, reviewer, action, notes, override_reason)
            VALUES (:rid, :reviewer, 'APPROVE', :notes, :override)
        """),
        {"rid": review_id, "reviewer": reviewer, "notes": notes, "override": override_reason},
    )

    # 解鎖 agent checkpoint
    await _unblock_checkpoint(db, review_id, "APPROVED")

    await _write_audit(db, "REVIEW_APPROVED", reviewer, review_id=review_id,
                       fund_id=req.fund_id, task_id=req.task_id,
                       details={"notes": notes, "override_reason": override_reason})
    await db.commit()
    logger.info("Review APPROVED: %s by %s", review_id, reviewer)
    return True


async def reject_review(
    db: AsyncSession,
    review_id: str,
    reviewer: str,
    reason: str,
) -> bool:
    """
    拒絕審核請求。agent checkpoint 收到通知後中止操作。
    reason 必填——是審計記錄的重要依據。
    """
    row = await db.execute(
        text("SELECT status, fund_id, task_id FROM fsi.review_requests WHERE review_id = :rid"),
        {"rid": review_id},
    )
    req = row.fetchone()
    if not req or req.status not in ("PENDING", "IN_REVIEW"):
        return False

    await db.execute(
        text("UPDATE fsi.review_requests SET status = 'REJECTED', updated_at = NOW() WHERE review_id = :rid"),
        {"rid": review_id},
    )
    await db.execute(
        text("""
            INSERT INTO fsi.review_decisions (review_id, reviewer, action, notes)
            VALUES (:rid, :reviewer, 'REJECT', :reason)
        """),
        {"rid": review_id, "reviewer": reviewer, "reason": reason},
    )

    await _unblock_checkpoint(db, review_id, "REJECTED")

    await _write_audit(db, "REVIEW_REJECTED", reviewer, review_id=review_id,
                       fund_id=req.fund_id, task_id=req.task_id,
                       details={"reason": reason})
    await db.commit()
    logger.info("Review REJECTED: %s by %s — %s", review_id, reviewer, reason)
    return True


async def get_pending_reviews(
    db: AsyncSession,
    fund_id: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """取待審核列表，按優先級+時間排序。"""
    sql = """
        SELECT r.review_id, r.category, r.status, r.priority,
               r.fund_id, r.as_of_date, r.title, r.summary,
               r.triggered_by, r.created_at, r.expires_at, r.sla_minutes,
               r.artefact_url, r.assigned_to,
               EXTRACT(EPOCH FROM (r.expires_at - NOW()))/60 AS remaining_minutes
        FROM fsi.review_requests r
        WHERE r.status IN ('PENDING', 'IN_REVIEW')
    """
    params: dict = {}
    if fund_id:
        sql += " AND r.fund_id = :fund_id"
        params["fund_id"] = fund_id
    if category:
        sql += " AND r.category = :category"
        params["category"] = category
    sql += " ORDER BY r.priority ASC, r.created_at ASC LIMIT :limit"
    params["limit"] = limit

    rows = await db.execute(text(sql), params)
    return [dict(r._mapping) for r in rows]


async def get_review_detail(db: AsyncSession, review_id: str) -> dict | None:
    """取審核詳情 + 決策歷史。"""
    row = await db.execute(
        text("SELECT * FROM fsi.review_requests WHERE review_id = :rid"),
        {"rid": review_id},
    )
    req = row.fetchone()
    if not req:
        return None

    decisions = await db.execute(
        text("SELECT * FROM fsi.review_decisions WHERE review_id = :rid ORDER BY decided_at"),
        {"rid": review_id},
    )
    checkpoints = await db.execute(
        text("SELECT * FROM fsi.agent_checkpoints WHERE review_id = :rid"),
        {"rid": review_id},
    )

    result = dict(req._mapping)
    result["decisions"] = [dict(d._mapping) for d in decisions]
    result["checkpoints"] = [dict(c._mapping) for c in checkpoints]
    return result


async def claim_review(db: AsyncSession, review_id: str, reviewer: str) -> bool:
    """審核員認領請求（IN_REVIEW 狀態）。"""
    await db.execute(
        text("""
            UPDATE fsi.review_requests
            SET status = 'IN_REVIEW', assigned_to = :reviewer, assigned_at = NOW()
            WHERE review_id = :rid AND status = 'PENDING'
        """),
        {"rid": review_id, "reviewer": reviewer},
    )
    await db.commit()
    return True


# ─── 內部輔助 ───────────────────────────────────────────────────

async def _write_audit(
    db: AsyncSession,
    event_type: str,
    actor: str,
    *,
    review_id: str | None = None,
    fund_id: str | None = None,
    task_id: str | None = None,
    details: dict | None = None,
) -> None:
    await db.execute(
        text("""
            INSERT INTO fsi.audit_log (event_type, actor, review_id, fund_id, task_id, details)
            VALUES (:evt, :actor, :rid, :fid, :tid, :details)
        """),
        {
            "evt": event_type, "actor": actor,
            "rid": review_id, "fid": fund_id, "tid": task_id,
            "details": json.dumps(details or {}),
        },
    )


async def _unblock_checkpoint(db: AsyncSession, review_id: str, action: str) -> None:
    """更新 agent_checkpoints 解鎖狀態，讓等待的 agent 繼續。"""
    await db.execute(
        text("""
            UPDATE fsi.agent_checkpoints
            SET unblocked_at = NOW(), unblock_action = :action
            WHERE review_id = :rid AND unblocked_at IS NULL
        """),
        {"rid": review_id, "action": action},
    )
