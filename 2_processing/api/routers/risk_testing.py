"""Standalone professional risk-testing API powered by FinancePy."""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Annotated, Any
from xml.etree import ElementTree

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...tools.risk_testing import ProfessionalRiskEngine, SCENARIOS, load_portfolio_snapshot, scenario_catalog
from ...tools.risk_testing.analytics import (
    krd,
    pnl_explain,
    reverse_stress,
    scenario as scenario_analytic,
    sensitivity,
    stress,
    tail_risk,
    var_backtest,
    xva,
)
from ...tools.risk_testing.financepy_adapter import FINANCEPY_CORE_CALLS
from ...tools.risk_testing.models import RiskFactorType, Scenario, Shock, ShockMode
from ..deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


class AnalyticType(str, Enum):
    """Business analytics exposed as independent GUI submenus."""

    SENSITIVITY = "SENSITIVITY"
    STRESS = "STRESS"
    SCENARIO = "SCENARIO"
    REVERSE_STRESS = "REVERSE_STRESS"
    TAIL_RISK = "TAIL_RISK"
    KRD = "KRD"
    PNL_EXPLAIN = "PNL_EXPLAIN"
    VAR_BACKTEST = "VAR_BACKTEST"
    XVA = "XVA"


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

    try:
        import financepy
        financepy_version = getattr(financepy, "__version__", "installed")
        financepy_available = True
    except ImportError:
        financepy_version = None
        financepy_available = False
    return {
        "module": "risk_testing",
        "engine": "FinancePy Professional Risk Engine",
        "financepy_available": financepy_available,
        "financepy_version": financepy_version,
        "analytics": [item.value for item in AnalyticType],
        "python_modules": {
            "SENSITIVITY": "risk_testing.analytics.sensitivity.run",
            "STRESS": "risk_testing.analytics.stress.run",
            "SCENARIO": "risk_testing.analytics.scenario.run",
            "REVERSE_STRESS": "risk_testing.analytics.reverse_stress.run",
            "TAIL_RISK": "risk_testing.analytics.tail_risk.run",
            "KRD": "risk_testing.analytics.krd.run",
            "PNL_EXPLAIN": "risk_testing.analytics.pnl_explain.run",
            "VAR_BACKTEST": "risk_testing.analytics.var_backtest.run",
            "XVA": "risk_testing.analytics.xva.run",
        },
        "data_modules": {
            "portfolio": "risk_testing.portfolio_data",
            "market": "risk_testing.market_data",
            "orchestrator": "risk_testing.loader.load_portfolio_snapshot",
        },
        "financepy_core_calls": FINANCEPY_CORE_CALLS,
        "interfaces": ["REST JSON", "REST XML", "Python", "Jupyter", "Excel/LibreOffice CSV"],
        "scenarios": scenario_catalog(),
    }


@router.post("/run/{fund_id}", summary="运行专业风险测试")
async def run_risk_test(
    fund_id: str,
    request: Annotated[RiskRunRequest, Body(...)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run one standalone risk analytic against existing ARISK portfolio data."""

    return await _execute(fund_id, request, db)


async def _execute(
    fund_id: str,
    request: RiskRunRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    """Execute a validated JSON or XML risk configuration."""

    try:
        snapshot = await load_portfolio_snapshot(fund_id, request.as_of_date, db, request.lookback_days)
        engine = ProfessionalRiskEngine(snapshot)
        if request.analytic == AnalyticType.SENSITIVITY:
            shocks = tuple(item.to_domain() for item in request.shocks) or _default_sensitivities()
            return sensitivity.run(engine, shocks)
        if request.analytic == AnalyticType.STRESS:
            return stress.run(engine, _scenario(request))
        if request.analytic == AnalyticType.SCENARIO:
            return scenario_analytic.run(engine, _scenario(request))
        if request.analytic == AnalyticType.REVERSE_STRESS:
            return reverse_stress.run(
                engine,
                _scenario(request),
                request.target_loss_pct_nav,
                request.max_reverse_scale,
            )
        if request.analytic == AnalyticType.TAIL_RISK:
            capital = snapshot.net_asset * request.capital_buffer_pct_nav / 100.0
            return tail_risk.run(engine, request.sigma_levels, capital)
        if request.analytic == AnalyticType.KRD:
            return krd.run(engine, request.rate_bump_bps)
        if request.analytic == AnalyticType.PNL_EXPLAIN:
            start_date = request.start_date or request.as_of_date - timedelta(days=30)
            if start_date >= request.as_of_date:
                raise HTTPException(status_code=422, detail="start_date must be earlier than as_of_date")
            previous = await load_portfolio_snapshot(fund_id, start_date, db, request.lookback_days)
            return pnl_explain.run(engine, previous)
        if request.analytic == AnalyticType.VAR_BACKTEST:
            return var_backtest.run(engine, request.confidence, request.backtest_window)
        if request.analytic == AnalyticType.XVA:
            return xva.run(
                engine,
                request.counterparty_hazard,
                request.own_hazard,
                request.recovery_rate,
                request.funding_spread,
                request.initial_margin_pct,
                request.mva_funding_spread,
            )
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="FinancePy is not installed in the processing runtime") from exc
    raise HTTPException(status_code=422, detail="Unsupported analytic")


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
