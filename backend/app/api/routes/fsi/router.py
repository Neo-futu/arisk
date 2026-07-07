"""FSI 業務路由聚合器 — 掛載在 /api/v1/fsi 下。

所有 FSI 業務路由均需 JWT 認證，通過 deps.ProcessingClient 代理到 2_processing 服務。
"""
from fastapi import APIRouter

from .agent import router as agent_router
from .positions import router as positions_router
from .risk import router as risk_router

router = APIRouter()
router.include_router(agent_router, prefix="/agent", tags=["FSI Agent / Chat"])
router.include_router(risk_router, prefix="/risk", tags=["FSI 風控"])
router.include_router(positions_router, prefix="/positions", tags=["FSI 持倉"])
