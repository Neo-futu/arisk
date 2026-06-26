"""FastAPI 日誌中間件：自動記錄所有 HTTP 請求/響應。

在 Processing API 和 Entry Web App 的 app.py 中注入：

    from 2_processing.logging.middleware import LoggingMiddleware
    app.add_middleware(LoggingMiddleware)
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .op_logger import OpLogger

_logger = OpLogger("http-middleware", actor_type="system")

# 不記錄日誌的路徑（健康檢查等）
SKIP_PATHS = {"/health", "/metrics", "/favicon.ico", "/static"}


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI 中間件：攔截每個 HTTP 請求，計時並寫操作日誌。

    記錄內容：
    - 請求方法、路徑、狀態碼
    - 執行耗時（ms）
    - 操作者（從 X-Reviewer-Id 或 Authorization header 提取）
    - 基金 ID（從路徑或 query string 提取）
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # 跳過不需要記錄的路徑
        if path in SKIP_PATHS or path.startswith("/static"):
            return await call_next(request)

        start = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)

            # 嘗試獲取 DB session（從 app.state 或 request.state）
            db = getattr(request.state, "db", None)
            if db is not None:
                actor = (
                    request.headers.get("X-Reviewer-Id")
                    or request.headers.get("X-User-Id")
                    or "anonymous"
                )
                fund_id = _extract_fund_id(path)
                session_id = request.headers.get("X-Session-Id")

                try:
                    await _logger.log_http(
                        db,
                        method=request.method,
                        path=path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        actor=actor,
                        fund_id=fund_id,
                        session_id=session_id,
                    )
                except Exception:
                    pass  # 日誌失敗不影響響應


def _extract_fund_id(path: str) -> str | None:
    """從路徑中提取 fund_id，例如 /positions/BHMMF → BHMMF。"""
    parts = [p for p in path.split("/") if p]
    known_prefixes = {"positions", "risk", "performance", "review"}
    for i, part in enumerate(parts):
        if part in known_prefixes and i + 1 < len(parts):
            candidate = parts[i + 1]
            # 簡單啟發式：fund_id 通常是大寫字母數字組合
            if candidate.upper() == candidate and len(candidate) <= 32:
                return candidate
    return None
