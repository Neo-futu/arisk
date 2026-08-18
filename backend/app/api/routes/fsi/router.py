"""FSI 業務路由聚合器 — 掛載在 /api/v1/fsi 下。

所有 FSI 業務路由均需 JWT 認證，通過 deps.ProcessingClient 代理到 2_processing 服務。
"""
from fastapi import APIRouter

from .agent import router as agent_router
from .indicator_sql import router as indicator_sql_router
from .investment import router as investment_router
from .positions import router as positions_router
from .reports import router as reports_router
from .risk import router as risk_router
from .risk_rules import router as risk_rules_router
from .schedules import router as schedules_router

router = APIRouter()
router.include_router(agent_router,   prefix="/agent",     tags=["FSI Agent / Chat"])
router.include_router(investment_router, prefix="/investment", tags=["FSI 投資風險分析"])
router.include_router(risk_router,    prefix="/risk",      tags=["FSI 風控"])
router.include_router(risk_rules_router, prefix="/risk-rules", tags=["FSI 風控規則配置"])
router.include_router(positions_router, prefix="/positions", tags=["FSI 持倉"])
router.include_router(reports_router, prefix="/reports",   tags=["FSI 報表"])
router.include_router(schedules_router, prefix="/schedules", tags=["FSI 定時報表"])
router.include_router(indicator_sql_router, prefix="/indicator-sql", tags=["FSI 指標SQL"])
