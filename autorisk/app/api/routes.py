from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from ..core.scenario import DemoScenarioCalculator
from ..schemas import (
    AssessRequest,
    DemoAssessRequest,
    RejectRequest,
    RiskEvalListResponse,
    SignRequest,
)
from ..security import verify_api_key
from ..service import RiskEvalService, WorkflowConflict

router = APIRouter(
    prefix="/risk-evals",
    tags=["risk-evals"],
    dependencies=[Depends(verify_api_key)],
)
service = RiskEvalService.default()
demo_calculator = DemoScenarioCalculator()


@router.post("/assess", status_code=status.HTTP_201_CREATED)
async def assess(req: AssessRequest):
    """Create an idempotent risk assessment and execute its configured workflow."""
    return await service.assess(req)


@router.post("/demo/assess", status_code=status.HTTP_201_CREATED)
async def assess_demo_scenario(req: DemoAssessRequest):
    """Calculate an add-position scenario and execute the complete risk workflow."""
    assess_request, calculated = demo_calculator.calculate(req)
    report = await service.assess(assess_request)
    return {"calculation": calculated, "report": report}


@router.get("/reports", response_model=RiskEvalListResponse)
async def list_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    fund_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    reports = service.list(status=status_filter, fund_code=fund_code, limit=limit)
    return RiskEvalListResponse(count=len(reports), reports=reports)


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    report = await service.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}/verify")
async def verify_report(report_id: str):
    result = service.verify_report(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found")
    return result


@router.post("/reports/{report_id}/sign/first")
async def sign_first(report_id: str, body: SignRequest):
    try:
        report = await service.first_sign(report_id, body)
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/reports/{report_id}/sign/second")
async def sign_second(report_id: str, body: SignRequest):
    try:
        report = await service.second_sign(report_id, body)
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/reports/{report_id}/reject")
async def reject(report_id: str, body: RejectRequest):
    try:
        report = service.reject(report_id, body)
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}/artifacts/{filename}")
async def download_artifact(report_id: str, filename: str):
    try:
        path = service.resolve_artifact(report_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    media_type = {
        ".json": "application/json",
        ".md": "text/markdown; charset=utf-8",
        ".html": "text/html; charset=utf-8",
    }.get(path.suffix, "application/octet-stream")
    return FileResponse(path=path, filename=path.name, media_type=media_type)


@router.get("/rules")
async def get_rules():
    return service.rules()


@router.post("/rules/reload")
async def reload_rules():
    return service.reload_rules()


@router.get("/audit")
async def list_audit(
    report_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
):
    events = service.list_audit(report_id=report_id, limit=limit)
    return {"count": len(events), "events": events}


@router.get("/audit/verify")
async def verify_audit():
    return service.verify_audit()
