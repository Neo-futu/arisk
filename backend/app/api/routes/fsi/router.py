"""FSI 業務路由聚合器 — 掛載在 /api/v1/fsi 下。

所有 FSI 業務路由均需 JWT 認證，通過 deps.ProcessingClient 代理到 2_processing 服務。
"""
from fastapi import APIRouter

from .agent import router as agent_router
from .data_management import router as data_management_router
from .indicator_explorer import router as indicator_explorer_router
from .indicator_sql import router as indicator_sql_router
from .portfolio_cockpit import router as portfolio_cockpit_router
from .portfolio_opt import router as portfolio_opt_router
from .investment import router as investment_router
from .positions import router as positions_router
from .reports import router as reports_router
from .risk import router as risk_router
from .risk_rules import router as risk_rules_router
from .schedules import router as schedules_router
from .sql_assets import router as sql_assets_router
from .valuation import router as valuation_router

router = APIRouter()
router.include_router(agent_router,   prefix="/agent",     tags=["FSI Agent / Chat"])
router.include_router(data_management_router, prefix="/data-management", tags=["FSI 數據管理中心"])
router.include_router(indicator_explorer_router, prefix="/indicator-explorer", tags=["FSI 指標探索"])
router.include_router(valuation_router, prefix="/valuation", tags=["FSI 估值與損益"])
router.include_router(portfolio_cockpit_router, prefix="/portfolio-cockpit", tags=["FSI 組合駕駛艙"])
router.include_router(portfolio_opt_router, prefix="/portfolio-opt", tags=["FSI 組合優化"])
router.include_router(sql_assets_router, prefix="/sql-assets", tags=["FSI SQL 資產庫"])
router.include_router(investment_router, prefix="/investment", tags=["FSI 投資風險分析"])
router.include_router(risk_router,    prefix="/risk",      tags=["FSI 風控"])
router.include_router(risk_rules_router, prefix="/risk-rules", tags=["FSI 風控規則配置"])
router.include_router(positions_router, prefix="/positions", tags=["FSI 持倉"])
router.include_router(reports_router, prefix="/reports",   tags=["FSI 報表"])
router.include_router(schedules_router, prefix="/schedules", tags=["FSI 定時報表"])
router.include_router(indicator_sql_router, prefix="/indicator-sql", tags=["FSI 指標SQL"])
