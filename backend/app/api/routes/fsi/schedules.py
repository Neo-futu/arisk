"""定時報表代理路由 — JWT 認證後轉發到 processing:8001/schedules。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, ProcessingClient, SessionDep
from app.services.portfolio_access import ensure_portfolio_access, list_accessible_portfolios

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


async def _authorized_schedule(
    sid: str,
    user: CurrentUser,
    session: SessionDep,
    client: ProcessingClient,
) -> dict[str, Any]:
    schedules = await _proxy(client, "get", "/schedules/")
    schedule = next((item for item in schedules if item.get("schedule_id") == sid), None)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    fund_id = schedule.get("fund_id")
    if not fund_id:
        raise HTTPException(status_code=502, detail="Schedule is missing portfolio ownership")
    ensure_portfolio_access(session, user, str(fund_id), "VIEW")
    return schedule


@router.get("/",            summary="查詢所有定時任務")
async def list_schedules(user: CurrentUser, session: SessionDep, c: ProcessingClient):
    allowed = {str(item["port_id"]) for item in list_accessible_portfolios(session, user)}
    schedules = await _proxy(c, "get", "/schedules/")
    return [item for item in schedules if str(item.get("fund_id")) in allowed]

@router.post("/",           summary="新建定時任務")
async def create_schedule(req: ScheduleCreate, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    ensure_portfolio_access(session, user, req.fund_id, "VIEW")
    return await _proxy(c, "post", "/schedules/", json=req.model_dump())

@router.patch("/{sid}",     summary="更新定時任務")
async def update_schedule(sid: str, req: ScheduleUpdate, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    await _authorized_schedule(sid, user, session, c)
    if req.fund_id:
        ensure_portfolio_access(session, user, req.fund_id, "VIEW")
    return await _proxy(c, "patch", f"/schedules/{sid}", json=req.model_dump(exclude_none=True))

@router.delete("/{sid}",    summary="刪除定時任務")
async def delete_schedule(sid: str, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    await _authorized_schedule(sid, user, session, c)
    return await _proxy(c, "delete", f"/schedules/{sid}")

@router.post("/{sid}/run-now", summary="立即執行")
async def run_now(sid: str, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    await _authorized_schedule(sid, user, session, c)
    return await _proxy(c, "post", f"/schedules/{sid}/run-now")

@router.get("/history/all", summary="全部歷史")
async def all_history(user: CurrentUser, session: SessionDep, c: ProcessingClient, limit: int = 100):
    allowed = {str(item["port_id"]) for item in list_accessible_portfolios(session, user)}
    history = await _proxy(c, "get", "/schedules/history/all", params={"limit": limit})
    return [item for item in history if str(item.get("fund_id")) in allowed]

@router.get("/{sid}/history", summary="單任務歷史")
async def schedule_history(sid: str, user: CurrentUser, session: SessionDep, c: ProcessingClient, limit: int = 50):
    await _authorized_schedule(sid, user, session, c)
    return await _proxy(c, "get", f"/schedules/{sid}/history", params={"limit": limit})

@router.get("/{sid}/files", summary="已生成文件列表")
async def list_files(sid: str, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    await _authorized_schedule(sid, user, session, c)
    return await _proxy(c, "get", f"/schedules/{sid}/files")

@router.get("/{sid}/download/{filename}", summary="下載歷史文件")
async def download_file(sid: str, filename: str, user: CurrentUser, session: SessionDep, c: ProcessingClient):
    await _authorized_schedule(sid, user, session, c)
    resp = await c.get(f"/schedules/{sid}/download/{filename}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return StreamingResponse(
        iter([resp.content]),
        media_type=resp.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": resp.headers.get("content-disposition", f'attachment; filename="{filename}"')},
    )
