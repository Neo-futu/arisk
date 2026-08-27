"""統一 backend 入口：把 arisk 的額外服務作為子應用掛載進同一個 FastAPI 進程。

對齊 ideclare 的「單 ECS 任務 = 一個對外 backend」形態：一個 uvicorn 進程即
對外服務，`2_processing` / `6_entry` / `4_mcp` / `autorisk` 以子應用掛載於不同
路徑前綴，成為 backend 的不同模組。

- 本地日常仍可用 `scripts/dev.py` 的多進程各 part（互不影響）；`unified` 提供
  「單進程對外」能力，供容器 / ECS 使用。
- 服務目錄名以數字開頭（`2_processing` 等）非法 Python 標識符，用 importlib 掛載。
- 每個掛載包 try/except：缺依賴 / 導入失敗只跳過該子應用，不使整個進程崩潰；
  啟動日誌與 `/unified/health` 匯報掛載結果。

復用現有 `app.main:app`（已裝好 iam / 業務路由 + CORS + Sentry）。
"""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

# 復用現有 backend 應用（在其之上追加掛載）
from app.main import app

logger = logging.getLogger("arisk.unified")

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
