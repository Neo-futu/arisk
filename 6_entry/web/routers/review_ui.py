"""審核收件箱 Router — Web UI 審核員操作界面（轉發到 Processing API）。

這一層純粹是入口層的代理（proxy），所有業務邏輯在 Processing 層。
審核員通過 Web UI 或此 API 完成：認領 → 查看詳情 → 批准/拒絕。
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")

router = APIRouter()
_headers = {"X-API-Key": PROCESSING_API_KEY}


class ApproveBody(BaseModel):
    reviewer: str
    notes: str = ""
    override_reason: str = ""


class RejectBody(BaseModel):
    reviewer: str
    reason: str


class ClaimBody(BaseModel):
    reviewer: str


async def _proxy(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=PROCESSING_API_URL, headers=_headers, timeout=30) as c:
        resp = await getattr(c, method)(path, **kwargs)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@router.get("/inbox")
async def review_inbox(fund_id: str | None = None, category: str | None = None):
    """
    審核收件箱：返回所有待處理的審核請求。
    Web UI 審核頁的數據源，按優先級排序。
    """
    params = {}
    if fund_id:
        params["fund_id"] = fund_id
    if category:
        params["category"] = category
    return await _proxy("get", "/review/pending", params=params)


@router.get("/inbox/{review_id}")
async def review_detail(review_id: str):
    """取單個審核請求的完整詳情（payload + artefact URL + 決策歷史）。"""
    return await _proxy("get", f"/review/{review_id}")


@router.post("/inbox/{review_id}/claim")
async def claim_review(review_id: str, body: ClaimBody):
    """認領審核請求（IN_REVIEW 狀態，防止重複審核）。"""
    return await _proxy("post", f"/review/{review_id}/claim", json=body.model_dump())


@router.post("/inbox/{review_id}/approve")
async def approve_review(review_id: str, body: ApproveBody):
    """
    批准審核請求。

    批准後立即通過 Redis pub/sub 通知等待的 agent checkpoint 繼續執行。
    如違規仍存在但選擇批准，需填寫 override_reason（審計要求）。
    """
    return await _proxy("post", f"/review/{review_id}/approve", json=body.model_dump())


@router.post("/inbox/{review_id}/reject")
async def reject_review(review_id: str, body: RejectBody):
    """
    拒絕審核請求。

    拒絕後 agent checkpoint 立即收到通知並中止被保護的操作。
    reason 必填。
    """
    return await _proxy("post", f"/review/{review_id}/reject", json=body.model_dump())


@router.get("/audit-log")
async def audit_log(fund_id: str | None = None, limit: int = 100):
    """不可篡改審計日誌查詢（合規存檔）。"""
    params = {"limit": limit}
    if fund_id:
        params["fund_id"] = fund_id
    return await _proxy("get", "/review/history/audit-log", params=params)
