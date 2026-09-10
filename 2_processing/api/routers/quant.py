"""Quant REST — same contract as the Python Quant API."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])
_quant = import_module("5_integrations.quant")
_po = import_module("4_business.portfolio_optimization.service")

Namespace = Literal["risk", "portfolio", "valuation", "testing"]


class QuantRequest(BaseModel):
    holdings: dict[str, float] = Field(default_factory=dict)
    method: str = "hrp"
    analytic: str = "SENSITIVITY"
    scenario_id: str = "gfc_2008"
    confidence: float = 0.99


def _snapshot(req: QuantRequest):
    holdings = dict(req.holdings) or {"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1}
    return _po.snapshot_from_weights(holdings, fund_id="QUANT")


@router.get("/catalog", summary="Quant API 合同")
async def quant_catalog() -> dict[str, Any]:
    return _quant.catalog()


@router.post("/{namespace}/{method}", summary="Quant API 调用")
async def quant_call(namespace: Namespace, method: str, req: QuantRequest) -> dict[str, Any]:
    allowed = _quant.QUANT_CONTRACT.get(namespace)
    if not allowed or method not in allowed:
        raise HTTPException(status_code=404, detail="Unknown quant method")
    snapshot = _snapshot(req)
    kwargs: dict[str, Any] = {}
    if namespace == "risk" and method in {"var", "cvar"}:
        kwargs["confidence"] = req.confidence
    if namespace == "risk" and method == "stress":
        kwargs["scenario_id"] = req.scenario_id
    if namespace == "portfolio" and method == "optimize":
        kwargs["method"] = req.method
    if namespace == "testing" and method == "run":
        kwargs["analytic"] = req.analytic
    func = getattr(getattr(_quant, namespace), method)
    return func(snapshot, **kwargs)
