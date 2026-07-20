from fastapi import APIRouter

from app.api.routes import (
    api_keys,
    items,
    login,
    notifications,
    private,
    users,
    utils,
)
from app.api.routes.chat import router as chat_router
from app.api.routes.frontend_log import router as log_router
from app.api.routes.fsi.router import router as fsi_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.user_agent import router as user_agent_router
from app.api.routes.user_custom_tool import router as user_tool_router
from app.core.config import settings

api_router = APIRouter()

# ── 模板原有路由（認證 / 用戶管理 / 工具） ─────────────────────
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["User API Keys"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# ── 聊天歷史（持久化到 chatdb.chat_session / chatdb.chat_message） ──
api_router.include_router(chat_router, prefix="/chat",   tags=["Chat History"])
api_router.include_router(log_router,        prefix="/logs",        tags=["Frontend Logs"])
api_router.include_router(user_agent_router, prefix="/agent-config",  tags=["User Agent Config"])
api_router.include_router(user_tool_router,  prefix="/custom-tools",  tags=["User Custom Tools"])
api_router.include_router(knowledge_router,  prefix="/knowledge",    tags=["Knowledge Base"])

# ── FSI 業務路由（風控 / 持倉 / 合規，代理到 processing:8001） ─
api_router.include_router(fsi_router, prefix="/fsi")

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
