"""Agent REST — same kernel as 7_ai.runtime. API key required."""
from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])
_ai = import_module("7_ai")
_po = import_module("4_business.portfolio_optimization.service")
_auth = import_module("7_ai.auth")


class AgentRequest(BaseModel):
    message: str
    agent: str | None = None
    holdings: dict[str, float] = Field(default_factory=dict)
    fund_id: str = "TEST001"
    role: str = "analyst"
    apply_live: bool = False
    sim_id: str | None = None
    workflow: str | None = None


def _context(req: AgentRequest):
    holdings = dict(req.holdings) or {"BOND5Y": 0.6, "US_EQ": 0.3, "CASH": 0.1}
    snapshot = _po.snapshot_from_weights(holdings, fund_id=req.fund_id)
    extra: dict[str, Any] = {}
    if req.sim_id:
        extra["sim_id"] = req.sim_id
    if req.workflow:
        extra["workflow"] = req.workflow
    if req.apply_live:
        extra["authorized"] = True
    ctx = _auth.AgentContext(
        actor="processing-api",
        role=req.role,
        snapshot=snapshot,
        fund_id=req.fund_id,
        authorized_funds=frozenset({req.fund_id, "TEST001", "QUANT"}),
        extra=extra,
    )
    return ctx, extra


@router.get("/catalog", summary="Agent / tool / MCP 合同")
async def agent_catalog() -> dict[str, Any]:
    return _ai.catalog()


@router.post("/invoke", summary="Agent 调用（Intent → Tool → Business → RiskEngine）")
async def agent_invoke(req: AgentRequest) -> dict[str, Any]:
    ctx, extra = _context(req)
    result = _ai.run(req.message, agent=req.agent, context=ctx, extra=extra)
    if not result["ok"] and result.get("error", {}).get("code") in {"JWT", "ROLE", "PORTFOLIO", "API", "PERMISSION"}:
        raise HTTPException(status_code=403, detail=result["error"])
    return result
