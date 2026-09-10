"""Standalone professional risk-testing API powered by FinancePy."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from enum import Enum
from typing import Annotated, Any
from xml.etree import ElementTree

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from importlib import import_module

from ...tools.risk_testing import SCENARIOS, load_portfolio_snapshot, scenario_catalog
from ...tools.risk_testing.models import RiskFactorType, Scenario, Shock, ShockMode
from ..deps import get_db, verify_api_key

_risk_testing_service = import_module("4_business.risk_testing.service")

router = APIRouter(dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)


class AnalyticType(str, Enum):
    """Business analytics exposed as independent GUI submenus."""

    SENSITIVITY = "SENSITIVITY"
    STRESS = "STRESS"
    SCENARIO = "SCENARIO"
    REVERSE_STRESS = "REVERSE_STRESS"
    TAIL_RISK = "TAIL_RISK"
    KRD = "KRD"
    PNL_EXPLAIN = "PNL_EXPLAIN"
    HISTORICAL_BACKTEST = "HISTORICAL_BACKTEST"
    VAR_BACKTEST = "VAR_BACKTEST"
    XVA = "XVA"


class WeightMode(str, Enum):
    """How historical-backtest target weights are sourced."""

    CURRENT = "CURRENT"
    CUSTOM = "CUSTOM"


class ShockInput(BaseModel):
    """User-defined shock input."""

    factor_type: RiskFactorType
    value: float
    mode: ShockMode = ShockMode.ABSOLUTE
    tenor: str | None = None
    currency: str | None = None
    label: str = ""

    def to_domain(self) -> Shock:
        """Convert validated API input to the risk domain model."""

        return Shock(self.factor_type, self.value, self.mode, self.tenor, self.currency, self.label)


class RiskRunRequest(BaseModel):
    """Unified configuration for all professional risk analytics."""

    analytic: AnalyticType
    as_of_date: date
    start_date: date | None = None
    scenario_id: str = "gfc_2008"
    scenario_name: str = "Custom scenario"
    shocks: list[ShockInput] = Field(default_factory=list, max_length=50)
    rate_bump_bps: float = Field(default=1.0, ge=0.01, le=1000)
    target_loss_pct_nav: float = Field(default=10.0, gt=0, le=1000)
    max_reverse_scale: float = Field(default=20.0, gt=0, le=1000)
    sigma_levels: list[float] = Field(default_factory=lambda: [3.0, 4.0, 5.0], min_length=1, max_length=10)
    capital_buffer_pct_nav: float = Field(default=10.0, ge=0, le=1000)
    confidence: float = Field(default=0.99, gt=0.5, lt=1.0)
    backtest_window: int = Field(default=60, ge=20, le=1000)
    lookback_days: int = Field(default=500, ge=30, le=5000)
    weight_mode: WeightMode = WeightMode.CURRENT
    custom_weights: dict[str, float] = Field(default_factory=dict, max_length=500)
    counterparty_hazard: float = Field(default=0.02, ge=0, le=1)
    own_hazard: float = Field(default=0.01, ge=0, le=1)
    recovery_rate: float = Field(default=0.40, ge=0, le=1)
    funding_spread: float = Field(default=0.01, ge=-0.1, le=1)
    initial_margin_pct: float = Field(default=0.05, ge=0, le=1)
    mva_funding_spread: float = Field(default=0.008, ge=-0.1, le=1)


def _default_sensitivities() -> tuple[Shock, ...]:
    return (
        Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="利率 +1bp"),
        Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE, label="外汇 ±1%"),
        Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE, label="波动率 +10%"),
        Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="权益价格 ±1%"),
        Shock(RiskFactorType.CREDIT_SPREAD, 0.0001, ShockMode.ABSOLUTE, label="信用利差 +1bp"),
    )


def _scenario(request: RiskRunRequest) -> Scenario:
    if request.shocks:
        return Scenario(
            scenario_id="custom",
            name=request.scenario_name,
            category="custom",
            shocks=tuple(item.to_domain() for item in request.shocks),
            description="User-defined multi-factor scenario",
        )
    if request.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=422, detail="Unknown scenario_id")
    return SCENARIOS[request.scenario_id]


@router.get("/capabilities", summary="FinancePy 风险引擎能力与情景目录")
async def capabilities() -> dict[str, Any]:
    """Return runtime capabilities for Python/Jupyter/GUI clients."""

    return _risk_testing_service.capabilities_payload([item.value for item in AnalyticType])


@router.post("/run/{fund_id}", summary="运行专业风险测试")
async def run_risk_test(
    fund_id: str,
    request: Annotated[RiskRunRequest, Body(...)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run one standalone risk analytic against existing ARISK portfolio data."""

    return await _execute(fund_id, request, db)


@router.get("/holdings/{fund_id}", summary="历史回测当前持仓及权重")
async def historical_backtest_holdings(
    fund_id: str,
    as_of_date: Annotated[date, Query()],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return current snapshot weights so GUI users can create adjusted allocations."""

    snapshot = await load_portfolio_snapshot(fund_id, as_of_date, db, 30)
    return _risk_testing_service.holdings_payload(fund_id, as_of_date, snapshot)


def _period_start(request: RiskRunRequest, default_days: int = 365) -> date:
    start_date = request.start_date or request.as_of_date - timedelta(days=default_days)
    if start_date >= request.as_of_date:
        raise HTTPException(status_code=422, detail="start_date must be earlier than as_of_date")
    return start_date


async def _execute(
    fund_id: str,
    request: RiskRunRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    """Execute a validated JSON or XML risk configuration via 4_business."""

    return await _risk_testing_service.execute_risk_test(fund_id, request, db)


def _log_runtime_trace(fund_id: str, request: RiskRunRequest, result: dict[str, Any]) -> None:
    """Persist Python module and FinancePy chain in processing logs rather than frontend UI."""

    implementation = result.get("implementation")
    scenario = result.get("scenario") if isinstance(result.get("scenario"), dict) else None
    shocks = scenario.get("shocks") if isinstance(scenario, dict) else None
    logger.info(
        "risk-testing execution fund=%s analytic=%s scenario=%s implementation=%s shocks=%s",
        fund_id,
        request.analytic.value,
        request.scenario_id,
        json.dumps(implementation, ensure_ascii=True, default=str),
        json.dumps(shocks, ensure_ascii=True, default=str),
    )


def _xml_request(payload: bytes) -> RiskRunRequest:
    """Parse a compact ORE-style XML run configuration."""

    try:
        root = ElementTree.fromstring(payload)
        values: dict[str, Any] = dict(root.attrib)
        scenario_node = root.find("scenario")
        if scenario_node is not None:
            values["scenario_id"] = scenario_node.get("id", "gfc_2008")
            values["scenario_name"] = scenario_node.get("name", "XML scenario")
        parameters = root.find("parameters")
        if parameters is not None:
            values.update(parameters.attrib)
        shocks: list[dict[str, Any]] = []
        for node in root.findall("./shocks/shock"):
            shocks.append(dict(node.attrib))
        if shocks:
            values["shocks"] = shocks
        for key in (
            "rate_bump_bps", "target_loss_pct_nav", "max_reverse_scale",
            "capital_buffer_pct_nav", "confidence", "counterparty_hazard",
            "own_hazard", "recovery_rate", "funding_spread",
            "initial_margin_pct", "mva_funding_spread",
        ):
            if key in values:
                values[key] = float(values[key])
        for key in ("backtest_window", "lookback_days"):
            if key in values:
                values[key] = int(values[key])
        sigma = values.get("sigma_levels")
        if isinstance(sigma, str):
            values["sigma_levels"] = [float(item.strip()) for item in sigma.split(",")]
        for shock in shocks:
            shock["value"] = float(shock["value"])
        return RiskRunRequest.model_validate(values)
    except (ElementTree.ParseError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid risk-testing XML: {exc}") from exc


@router.post("/run-xml/{fund_id}", summary="使用 XML 配置运行专业风险测试")
async def run_risk_test_xml(
    fund_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run the same engine through an XML configuration interface."""

    configuration = _xml_request(await request.body())
    return await _execute(fund_id, configuration, db)


@router.get("/catalog", summary="风险测试情景目录")
async def catalog(
    category: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    rows = scenario_catalog()
    if category:
        rows = [row for row in rows if row["category"] == category]
    return {"items": rows, "count": len(rows)}
