"""報表生成代理路由 — 轉發到 2_processing FastAPI（processing:8001/reports）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser, ProcessingClient

router = APIRouter()


class GenerateRequest(BaseModel):
    report_id: str
    fund_id: str
    as_of_date: str


@router.post("/generate", summary="觸發報表生成任務")
async def proxy_generate(
    req: GenerateRequest,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    resp = await client.post("/reports/generate", json=req.model_dump())
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/result/{report_id}", summary="查詢已生成文件（頁面刷新後恢復）")
async def proxy_result(
    report_id: str,
    fund_id: str,
    as_of_date: str,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    resp = await client.get(
        f"/reports/result/{report_id}",
        params={"fund_id": fund_id, "as_of_date": as_of_date},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/tasks/{task_id}", summary="查詢任務進度")
async def proxy_task_status(
    task_id: str,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    resp = await client.get(f"/reports/tasks/{task_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/download/{report_id}/{filename}", summary="下載報表文件")
async def proxy_download(
    report_id: str,
    filename: str,
    _user: CurrentUser,
    client: ProcessingClient,
):
    """串流代理下載，直接把 processing 返回的文件流透傳給瀏覽器。"""
    from fastapi.responses import StreamingResponse

    resp = await client.get(
        f"/reports/download/{report_id}/{filename}",
        follow_redirects=True,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    content_type = resp.headers.get("content-type", "application/octet-stream")
    content_disp = resp.headers.get(
        "content-disposition",
        f'attachment; filename="{filename}"',
    )
    return StreamingResponse(
        iter([resp.content]),
        media_type=content_type,
        headers={"Content-Disposition": content_disp},
    )
