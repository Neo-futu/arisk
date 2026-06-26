"""操作日誌查詢 API Router。"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

LOG_LEVELS    = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_CATS      = (
    "API_ACCESS","AGENT_ACTION","REVIEW_EVENT","ETL_JOB","RISK_CALC",
    "PERF_CALC","MCP_CALL","AUTH","SYSTEM","DATA_WRITE","SCHEDULER",
)


@router.get("/")
async def query_logs(
    level:      str | None = Query(None, description=f"級別: {LOG_LEVELS}"),
    category:   str | None = Query(None, description=f"類別: {LOG_CATS}"),
    actor:      str | None = Query(None, description="操作者 ID / agent 名"),
    fund_id:    str | None = Query(None),
    task_id:    str | None = Query(None),
    review_id:  str | None = Query(None),
    status:     str | None = Query(None, description="ok / error / blocked / timeout"),
    since:      datetime | None = Query(None, description="開始時間 ISO8601"),
    until:      datetime | None = Query(None, description="結束時間 ISO8601"),
    min_duration_ms: int | None = Query(None, description="最小耗時（ms），用於慢查詢篩選"),
    limit:      int = Query(100, le=1000),
    offset:     int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """
    查詢操作日誌。支援多維度篩選：

    常用場景：
    - 查詢某基金的所有操作：`?fund_id=BHMMF`
    - 查詢慢操作：`?min_duration_ms=2000`
    - 查詢錯誤：`?level=ERROR`
    - 查詢審核流程事件：`?category=REVIEW_EVENT`
    - 查詢小富 AI 操作：`?actor=小富`
    """
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if level:
        conditions.append("level = :level")
        params["level"] = level
    if category:
        conditions.append("category = :category")
        params["category"] = category
    if actor:
        conditions.append("actor ILIKE :actor")
        params["actor"] = f"%{actor}%"
    if fund_id:
        conditions.append("fund_id = :fund_id")
        params["fund_id"] = fund_id
    if task_id:
        conditions.append("task_id = :task_id")
        params["task_id"] = task_id
    if review_id:
        conditions.append("review_id = :review_id::uuid")
        params["review_id"] = review_id
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if since:
        conditions.append("log_time >= :since")
        params["since"] = since
    if until:
        conditions.append("log_time <= :until")
        params["until"] = until
    if min_duration_ms is not None:
        conditions.append("duration_ms >= :min_dur")
        params["min_dur"] = min_duration_ms

    where = " AND ".join(conditions)
    sql = f"""
        SELECT log_id, log_time, level, category, actor, actor_type, action,
               fund_id, task_id, review_id, http_method, http_path, http_status,
               duration_ms, status, detail, extra
        FROM fsi.op_logs
        WHERE {where}
        ORDER BY log_time DESC
        LIMIT :limit OFFSET :offset
    """
    rows = await db.execute(text(sql), params)
    logs = [dict(r._mapping) for r in rows]

    # 統計總數（用於分頁）
    count_sql = f"SELECT COUNT(*) FROM fsi.op_logs WHERE {where}"
    count_row = await db.execute(
        text(count_sql),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_row.scalar() or 0

    return {"total": total, "offset": offset, "limit": limit, "logs": logs}


@router.get("/summary")
async def log_summary(
    since: datetime | None = Query(None),
    fund_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    日誌彙總統計：各類別/級別的計數，用於儀表板概覽。
    """
    conditions = ["1=1"]
    params: dict = {}
    if since:
        conditions.append("log_time >= :since")
        params["since"] = since
    if fund_id:
        conditions.append("fund_id = :fund_id")
        params["fund_id"] = fund_id
    where = " AND ".join(conditions)

    by_level = await db.execute(
        text(f"SELECT level, COUNT(*) as cnt FROM fsi.op_logs WHERE {where} GROUP BY level"),
        params,
    )
    by_category = await db.execute(
        text(f"SELECT category, COUNT(*) as cnt FROM fsi.op_logs WHERE {where} GROUP BY category ORDER BY cnt DESC"),
        params,
    )
    error_rate = await db.execute(
        text(f"""
            SELECT
                COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                COUNT(*) AS total_count,
                AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) AS avg_duration_ms
            FROM fsi.op_logs WHERE {where}
        """),
        params,
    )
    er = dict(error_rate.fetchone()._mapping)

    return {
        "by_level":    {r.level: r.cnt for r in by_level},
        "by_category": {r.category: r.cnt for r in by_category},
        "error_count":    er.get("error_count", 0),
        "total_count":    er.get("total_count", 0),
        "avg_duration_ms": round(float(er.get("avg_duration_ms") or 0), 1),
    }


@router.get("/slow-ops")
async def slow_operations(
    threshold_ms: int = Query(2000, description="耗時閾值（ms）"),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    """查詢慢操作（用於性能排查）。"""
    rows = await db.execute(
        text("""
            SELECT action, category, actor, fund_id, duration_ms, log_time, status
            FROM fsi.op_logs
            WHERE duration_ms >= :threshold
            ORDER BY duration_ms DESC
            LIMIT :limit
        """),
        {"threshold": threshold_ms, "limit": limit},
    )
    return {"threshold_ms": threshold_ms, "ops": [dict(r._mapping) for r in rows]}
