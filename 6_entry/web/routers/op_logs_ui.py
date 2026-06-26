"""操作日誌 UI Router — 代理到 Processing API 的日誌查詢。"""
from __future__ import annotations

import os
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Query

PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")

router = APIRouter()
_headers = {"X-API-Key": PROCESSING_API_KEY}


async def _proxy_get(path: str, params: dict) -> dict:
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=_headers, timeout=30) as c:
        resp = await c.get(path, params={k: v for k, v in params.items() if v is not None})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@router.get("/")
async def get_logs(
    level:           str | None = Query(None),
    category:        str | None = Query(None),
    actor:           str | None = Query(None),
    fund_id:         str | None = Query(None),
    task_id:         str | None = Query(None),
    review_id:       str | None = Query(None),
    status:          str | None = Query(None),
    since:           datetime | None = Query(None),
    until:           datetime | None = Query(None),
    min_duration_ms: int | None = Query(None),
    limit:           int = Query(100),
    offset:          int = Query(0),
):
    """日誌查詢（代理到 Processing API）。"""
    return await _proxy_get("/op-logs/", {
        "level": level, "category": category, "actor": actor,
        "fund_id": fund_id, "task_id": task_id, "review_id": review_id,
        "status": status, "since": since, "until": until,
        "min_duration_ms": min_duration_ms, "limit": limit, "offset": offset,
    })


@router.get("/summary")
async def log_summary(
    since:   datetime | None = Query(None),
    fund_id: str | None = Query(None),
):
    """日誌彙總統計（儀表板用）。"""
    return await _proxy_get("/op-logs/summary", {"since": since, "fund_id": fund_id})


@router.get("/slow-ops")
async def slow_ops(threshold_ms: int = Query(2000), limit: int = Query(20)):
    """慢操作查詢（性能排查）。"""
    return await _proxy_get("/op-logs/slow-ops", {"threshold_ms": threshold_ms, "limit": limit})
