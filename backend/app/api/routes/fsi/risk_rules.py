"""Unified risk-rule configuration proxy — superuser only."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, ProcessingClient, SessionDep
from app.models import User
from app.services.portfolio_access import ensure_global_permission


def require_risk_rule_manager(
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_global_permission(session, current_user, "risk_rules.manage")
    return current_user


router = APIRouter(dependencies=[Depends(require_risk_rule_manager)])
RuleType = Literal["regulatory", "contract", "internal"]


async def _proxy(client: ProcessingClient, method: str, path: str, **kwargs: Any) -> Any:
    if "params" in kwargs and kwargs["params"] is not None:
        kwargs["params"] = {
            key: value
            for key, value in kwargs["params"].items()
            if value is not None and value != ""
        }
    response = await getattr(client, method)(path, **kwargs)
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@router.get("/", summary="统一查询监管、合同和内部风控规则")
async def list_risk_rules(
    _user: CurrentUser,
    client: ProcessingClient,
    rule_type: RuleType | None = None,
    fund_id: str | None = None,
    active_only: bool = False,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> Any:
    return await _proxy(
        client,
        "get",
        "/risk-rules/",
        params={
            "rule_type": rule_type,
            "fund_id": fund_id,
            "active_only": active_only,
            "search": search,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get("/summary", summary="风控规则分类统计")
async def risk_rule_summary(_user: CurrentUser, client: ProcessingClient) -> Any:
    return await _proxy(client, "get", "/risk-rules/summary")


@router.get("/{rule_type}/{rule_id}", summary="查询单条风控规则")
async def get_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(client, "get", f"/risk-rules/{rule_type}/{rule_id}")


@router.post("/", status_code=201, summary="创建风控规则")
async def create_risk_rule(
    current_user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    data = dict(payload)
    data["created_by"] = str(current_user.id)
    return await _proxy(client, "post", "/risk-rules/", json=data)


@router.patch("/{rule_type}/{rule_id}", summary="更新风控规则")
async def update_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    current_user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    data = dict(payload)
    data["updated_by"] = str(current_user.id)
    return await _proxy(
        client,
        "patch",
        f"/risk-rules/{rule_type}/{rule_id}",
        json=data,
    )


@router.delete("/{rule_type}/{rule_id}", summary="停用风控规则")
async def deactivate_risk_rule(
    rule_type: RuleType,
    rule_id: int,
    current_user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/risk-rules/{rule_type}/{rule_id}",
        params={"updated_by": str(current_user.id)},
    )


@router.get("/{rule_type}/{rule_id}/attachments", summary="查询规则附件")
async def list_risk_rule_attachments(
    rule_type: RuleType,
    rule_id: int,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(client, "get", f"/risk-rules/{rule_type}/{rule_id}/attachments")


@router.post("/{rule_type}/{rule_id}/attachments", summary="上传规则附件", status_code=201)
async def upload_risk_rule_attachment(
    rule_type: RuleType,
    rule_id: int,
    current_user: CurrentUser,
    client: ProcessingClient,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
) -> Any:
    content = await file.read()
    resp = await client.post(
        f"/risk-rules/{rule_type}/{rule_id}/attachments",
        data={"note": note or "", "created_by": str(current_user.id)},
        files={
            "file": (
                file.filename or "uploaded",
                content,
                file.content_type or "application/octet-stream",
            )
        },
    )
    if resp.status_code != 201:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/attachment-files/{attachment_id}/download", summary="下载规则附件")
async def download_risk_rule_attachment(
    attachment_id: int,
    _user: CurrentUser,
    client: ProcessingClient,
):
    resp = await client.get(f"/risk-rules/attachment-files/{attachment_id}/download")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return StreamingResponse(
        iter([resp.content]),
        media_type=resp.headers.get("content-type", "application/octet-stream"),
        headers={
            "Content-Disposition": resp.headers.get(
                "content-disposition",
                'attachment; filename="attachment.bin"',
            )
        },
    )


@router.delete("/attachment-files/{attachment_id}", summary="删除规则附件")
async def delete_risk_rule_attachment(
    attachment_id: int,
    _user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(client, "delete", f"/risk-rules/attachment-files/{attachment_id}")


@router.post("/regulatory/bootstrap", summary="补齐SFC监管基线规则")
async def bootstrap_regulatory_rules(
    _user: CurrentUser,
    client: ProcessingClient,
    effective_date: str = Query(default="2024-01-01"),
) -> Any:
    return await _proxy(
        client,
        "post",
        "/risk-rules/regulatory/bootstrap",
        params={"effective_date": effective_date},
    )


@router.get("/regulatory-brief", summary="监管规则简要列表")
async def regulatory_brief(
    _user: CurrentUser,
    client: ProcessingClient,
    fund_id: str | None = None,
    active_only: bool = True,
) -> Any:
    return await _proxy(
        client,
        "get",
        "/risk-rules/regulatory-brief",
        params={"fund_id": fund_id, "active_only": active_only},
    )


@router.get("/applications", summary="规则应用配置列表")
async def list_rule_applications(
    _user: CurrentUser,
    client: ProcessingClient,
    apply_scope: str | None = None,
    fund_id: str | None = None,
    active_only: bool = True,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> Any:
    return await _proxy(
        client,
        "get",
        "/risk-rules/applications",
        params={
            "apply_scope": apply_scope,
            "fund_id": fund_id,
            "active_only": active_only,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post("/applications", summary="创建规则应用配置", status_code=201)
async def create_rule_application(
    current_user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    data = dict(payload)
    data["created_by"] = str(current_user.id)
    return await _proxy(client, "post", "/risk-rules/applications", json=data)


@router.patch("/applications/item/{application_id}", summary="更新规则应用配置")
async def update_rule_application(
    application_id: int,
    current_user: CurrentUser,
    client: ProcessingClient,
    payload: dict[str, Any] = Body(...),
) -> Any:
    data = dict(payload)
    data["updated_by"] = str(current_user.id)
    return await _proxy(client, "patch", f"/risk-rules/applications/item/{application_id}", json=data)


@router.delete("/applications/item/{application_id}", summary="停用规则应用配置")
async def deactivate_rule_application(
    application_id: int,
    current_user: CurrentUser,
    client: ProcessingClient,
) -> Any:
    return await _proxy(
        client,
        "delete",
        f"/risk-rules/applications/item/{application_id}",
        params={"updated_by": str(current_user.id)},
    )
