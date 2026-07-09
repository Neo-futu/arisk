"""定時報表代理路由 — JWT 認證後轉發到 processing:8001/schedules。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, ProcessingClient

router = APIRouter()


class ScheduleCreate(BaseModel):
    name:      str
    report_id: str
    fund_id:   str
    hour:      int
    minute:    int
    enabled:   bool = True


class ScheduleUpdate(BaseModel):
    name:      str  | None = None
    report_id: str  | None = None
    fund_id:   str  | None = None
    hour:      int  | None = None
    minute:    int  | None = None
    enabled:   bool | None = None


async def _proxy(client: ProcessingClient, method: str, path: str, **kwargs) -> Any:
    resp = await getattr(client, method)(path, **kwargs)
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/",            summary="查詢所有定時任務")
async def list_schedules(_u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "get", "/schedules/")

@router.post("/",           summary="新建定時任務")
async def create_schedule(req: ScheduleCreate, _u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "post", "/schedules/", json=req.model_dump())

@router.patch("/{sid}",     summary="更新定時任務")
async def update_schedule(sid: str, req: ScheduleUpdate, _u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "patch", f"/schedules/{sid}", json=req.model_dump(exclude_none=True))

@router.delete("/{sid}",    summary="刪除定時任務")
async def delete_schedule(sid: str, _u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "delete", f"/schedules/{sid}")

@router.post("/{sid}/run-now", summary="立即執行")
async def run_now(sid: str, _u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "post", f"/schedules/{sid}/run-now")

@router.get("/history/all", summary="全部歷史")
async def all_history(_u: CurrentUser, c: ProcessingClient, limit: int = 100):
    return await _proxy(c, "get", "/schedules/history/all", params={"limit": limit})

@router.get("/{sid}/history", summary="單任務歷史")
async def schedule_history(sid: str, _u: CurrentUser, c: ProcessingClient, limit: int = 50):
    return await _proxy(c, "get", f"/schedules/{sid}/history", params={"limit": limit})

@router.get("/{sid}/files", summary="已生成文件列表")
async def list_files(sid: str, _u: CurrentUser, c: ProcessingClient):
    return await _proxy(c, "get", f"/schedules/{sid}/files")

@router.get("/{sid}/download/{filename}", summary="下載歷史文件")
async def download_file(sid: str, filename: str, _u: CurrentUser, c: ProcessingClient):
    resp = await c.get(f"/schedules/{sid}/download/{filename}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return StreamingResponse(
        iter([resp.content]),
        media_type=resp.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": resp.headers.get("content-disposition", f'attachment; filename="{filename}"')},
    )
