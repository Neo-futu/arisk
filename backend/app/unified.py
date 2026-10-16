"""統一 backend 入口：把 arisk 的額外服務作為子應用掛載進同一個 FastAPI 進程。

對齊 ideclare 的「單 ECS 任務 = 一個對外 backend」形態：一個 uvicorn 進程即
對外服務，`2_processing` / `6_entry` / `4_mcp` / `autorisk` 以子應用掛載於不同
路徑前綴，成為 backend 的不同模組。

- 本地日常仍可用 `scripts/dev.py` 的多進程各 part（互不影響）；`unified` 提供
  「單進程對外」能力，供容器 / ECS 使用。
- 服務目錄名以數字開頭（`2_processing` 等）非法 Python 標識符，用 importlib 掛載。
- 每個掛載包 try/except：缺依賴 / 導入失敗只跳過該子應用，不使整個進程崩潰；
  啟動日誌與 `/unified/health` 匯報掛載結果。

本文件顯式構建 FastAPI 應用並掛載 backend API router，避免熱重載下
對外核心路由偶發丟失（例如 /api/v1/users/me 被 404）。

注意：2_processing 等子模塊改動若未觸發重載，可輕觸本文件强制 reload。
# touch: lqa computed from holdings 2026-10-16
"""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings

logger = logging.getLogger("arisk.unified")


def _custom_generate_unique_id(route: APIRoute) -> str:
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=_custom_generate_unique_id,
)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 先掛核心 /api/v1 路由，再掛子應用，確保前端初始化請求穩定命中。
app.include_router(api_router, prefix=settings.API_V1_STR)

# repo 根加入 sys.path，便於導入數字名子應用包（2_processing / 6_entry / 4_mcp）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# (掛載路徑, 模組, app 變量名)
_SUBAPPS = [
    ("/processing", "2_processing.api.main", "app"),
    ("/entry", "6_entry.web.app", "app"),
    ("/mcp", "4_mcp.gateway.mcp_gateway", "app"),
    ("/autorisk", "autorisk.app.main", "app"),
]

_mounted: list[str] = []
_skipped: list[dict[str, str]] = []

for path, module_name, attr in _SUBAPPS:
    try:
        module = importlib.import_module(module_name)
        subapp = getattr(module, attr)
        app.mount(path, subapp)
        _mounted.append(path)
        logger.info("已掛載 %s ← %s:%s", path, module_name, attr)
    except Exception as exc:  # noqa: BLE001 — 缺依賴/導入失敗只跳過該子應用
        _skipped.append({"path": path, "module": module_name, "error": repr(exc)})
        logger.warning("跳過掛載 %s (%s)：%s", path, module_name, exc)

logger.info("unified backend 掛載完成 mounted=%s skipped=%s",
            _mounted, [s["path"] for s in _skipped])


@app.get("/unified/health", tags=["unified"])
def unified_health() -> dict[str, object]:
    """匯報統一入口的子應用掛載情況。"""
    return {"status": "ok", "mounted": _mounted, "skipped": _skipped}
