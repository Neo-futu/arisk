from fastapi import APIRouter

from app.api.routes import items, login, private, users, utils
from app.api.routes.fsi.router import router as fsi_router
from app.core.config import settings

api_router = APIRouter()

# ── 模板原有路由（認證 / 用戶管理 / 工具） ─────────────────────
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)

# ── FSI 業務路由（風控 / 持倉 / 合規，代理到 processing:8001） ─
api_router.include_router(fsi_router, prefix="/fsi")

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
