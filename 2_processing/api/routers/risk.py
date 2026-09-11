"""風控 API Router。"""
from datetime import date
from importlib import import_module
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, verify_api_key
from ...tools.risk.exposure_engine import compute_exposure, find_latest_exposure_date
from ...tools.risk.var_calculator import (
    compute_distribution_var,
    compute_historical_var,
    compute_monte_carlo_var,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])
_gov = import_module("4_business.risk_governance.service")
_pre = import_module("4_business.risk_governance.pre_trade")
_po = import_module("4_business.portfolio_optimization.service")
_Unauthorized = _gov.Unauthorized
_HardLocked = _gov.HardBreachLocked


@router.get("/exposure-latest-date/{fund_id}")
async def get_exposure_latest_date(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="參考日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """返回基金在參考日期之前（含當天）的最新可用暴露數據日期。"""
    effective_date = await find_latest_exposure_date(fund_id=fund_id, as_of_date=as_of_date, db=db)
    return {
        "fund_id": fund_id,
        "requested_as_of_date": as_of_date,
        "effective_date": effective_date,
    }


@router.get("/exposure/{fund_id}")
async def get_exposure(
    fund_id: str,
    as_of_date: Annotated[date, Query(description="持倉日期 YYYY-MM-DD")],
    db: AsyncSession = Depends(get_db),
):
    """計算基金指定日期的暴露指標及 MMF 合規狀態。"""
    result = await compute_exposure(fund_id, as_of_date, db)
    return {
        "fund_id": result.fund_id,
        "as_of_date": result.as_of_date,
        "total_nav_hkd": result.total_nav_hkd,
        "wam_days": result.wam_days,
        "wal_days": result.wal_days,
        "daily_liquid_pct": result.daily_liquid_pct,
        "weekly_liquid_pct": result.weekly_liquid_pct,
        "is_compliant": result.is_compliant,
        "breach_flags": list(result.breach_flags.keys()),
        "effective_limits": result.effective_limits,
        "compliance_details": result.compliance_details,
        "rule_trace": result.rule_trace,
        "by_asset_type": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                          for k, v in result.by_asset_type.items()},
        "by_currency": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                        for k, v in result.by_currency.items()},
        "by_maturity_bucket": {k: {"mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
                                for k, v in result.by_maturity_bucket.items()},
        "top_issuers": sorted(
            [{"issuer": k, "mv_hkd": v, "pct": v / result.total_nav_hkd * 100 if result.total_nav_hkd else 0}
             for k, v in result.by_issuer.items()],
            key=lambda x: x["pct"], reverse=True
        )[:10],
    }


@router.get("/var/{fund_id}")
async def get_var(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    confidence: float = 0.99,
    horizon_days: int = 1,
    method: str = "historical",
    simulations: int = 10000,
    db: AsyncSession = Depends(get_db),
):
    """計算基金 VaR。method: historical | monte_carlo | distribution。"""
    method_normalized = method.lower()
    if method_normalized == "historical":
        result = await compute_historical_var(fund_id, as_of_date, db, confidence, horizon_days)
    elif method_normalized in {"distribution", "parametric"}:
        result = await compute_distribution_var(fund_id, as_of_date, db, confidence, horizon_days)
    elif method_normalized in {"monte_carlo", "monte-carlo", "mc"}:
        result = await compute_monte_carlo_var(
            fund_id=fund_id,
            as_of_date=as_of_date,
            db=db,
            confidence=confidence,
            horizon_days=horizon_days,
            simulations=simulations,
        )
    else:
        result = await compute_historical_var(fund_id, as_of_date, db, confidence, horizon_days)

    return {
        "fund_id": result.fund_id,
        "as_of_date": result.as_of_date,
        "confidence": result.confidence,
        "horizon_days": result.horizon_days,
        "var_hkd": result.var_amount_hkd,
        "var_pct_nav": result.var_pct_nav,
        "cvar_hkd": result.cvar_amount_hkd,
        "method": result.method,
        "sample_size": result.sample_size,
    }


class PreTradeRequest(BaseModel):
    fund_id: str | None = None
    as_of_date: date | None = None
    security_code: str
    security_name: str | None = None
    side: Literal["BUY", "SELL"] = "BUY"
    amount: float
    asset_class: str = "EQUITY"
    currency: str | None = None
    issuer: str | None = None
    sector: str | None = None
    country: str | None = None
    counterparty: str | None = None
    duration: float = 0.0
    holdings: dict[str, float] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    exception_approved: bool = False
    actor: str = "system"
    lookback_days: int = Field(default=500, ge=30, le=5000)
    scenario_id: str = "gfc_2008"


class GovernanceMutation(BaseModel):
    case_id: str
    reason: str = ""
    note: str = ""
    authorized: bool = False
    actor: str = "system"


async def _snapshot_for_pretrade(req: PreTradeRequest, db: AsyncSession):
    if req.fund_id:
        as_of = req.as_of_date or date.today()
        return await _gov.load_snapshot(req.fund_id, as_of, db, req.lookback_days)
    holdings = dict(req.holdings)
    if not holdings:
        raise HTTPException(status_code=422, detail="fund_id or holdings is required")
    return _po.snapshot_from_weights(holdings, fund_id="SIM")


@router.get("/limits/catalog", summary="統一 Limit Engine 目錄")
async def limits_catalog() -> dict[str, Any]:
    return _gov.catalog()


@router.get("/governance/catalog", summary="風險治理目錄")
async def governance_catalog() -> dict[str, Any]:
    return _gov.catalog()


@router.post("/pre-trade", summary="前置風控：Order → Limit → APPROVE/WARNING/REJECT")
async def pre_trade(req: PreTradeRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    snapshot = await _snapshot_for_pretrade(req, db)
    return _pre.run_pre_trade(
        snapshot,
        req.model_dump(),
        policy=req.policy or None,
        scenario_id=req.scenario_id,
        exception_approved=req.exception_approved,
        actor=req.actor,
    )


@router.post("/governance/exception", summary="申請限额例外（需授權）")
async def governance_exception(req: GovernanceMutation) -> dict[str, Any]:
    try:
        return _gov.default_cases().request_exception(
            req.case_id, req.reason or req.note, authorized=req.authorized, actor=req.actor
        )
    except _Unauthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except _HardLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
