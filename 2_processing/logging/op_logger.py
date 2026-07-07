"""操作日誌模組 — 全平台結構化日誌，寫入 Postgres + 文件。

使用方式：
    from 2_processing.logging.op_logger import OpLogger

    logger = OpLogger("risk-calculator")

    # 記錄一次操作
    await logger.info(db, "compute_exposure",
        category="RISK_CALC",
        fund_id="BHMMF",
        detail="WAM=58.3天, WAL=112天",
        extra={"wam": 58.3, "wal": 112}
    )

    # 計時器（自動記錄 duration_ms）
    async with logger.timed(db, "compute_var", category="RISK_CALC", fund_id="BHMMF") as ctx:
        result = await do_var_calc(...)
        ctx.extra["var_pct"] = result.var_pct_nav
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── structlog 配置（文件 + 控制台結構化日誌）──────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

_HOST     = socket.gethostname()
_VERSION  = os.environ.get("APP_VERSION", "0.1.0")
_SERVICE  = "arisk"

std_log = structlog.get_logger()


@dataclass
class TimedContext:
    """計時器上下文，用於在 timed() 結束時附加 extra 數據。"""
    extra: dict = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None


class OpLogger:
    """
    操作日誌記錄器。每個模組實例化一個，傳入模組名作為默認 actor。
    """

    def __init__(self, actor: str, actor_type: str = "system"):
        self.actor = actor
        self.actor_type = actor_type
        self._slog = std_log.bind(actor=actor)

    # ─── 級別方法 ────────────────────────────────────────────────

    async def debug(self, db: AsyncSession, action: str, **kwargs) -> None:
        await self._write(db, "DEBUG", action, **kwargs)

    async def info(self, db: AsyncSession, action: str, **kwargs) -> None:
        await self._write(db, "INFO", action, **kwargs)

    async def warning(self, db: AsyncSession, action: str, **kwargs) -> None:
        await self._write(db, "WARNING", action, **kwargs)

    async def error(self, db: AsyncSession, action: str, **kwargs) -> None:
        await self._write(db, "ERROR", action, **kwargs)

    async def critical(self, db: AsyncSession, action: str, **kwargs) -> None:
        await self._write(db, "CRITICAL", action, **kwargs)

    # ─── 計時器上下文管理器 ──────────────────────────────────────

    @asynccontextmanager
    async def timed(
        self,
        db: AsyncSession,
        action: str,
        *,
        category: str,
        level: str = "INFO",
        fund_id: str | None = None,
        task_id: str | None = None,
        review_id: str | None = None,
        **extra_kwargs: Any,
    ) -> AsyncIterator[TimedContext]:
        """
        自動計時並記錄 duration_ms 的上下文管理器。

        使用：
            async with logger.timed(db, "load_positions", category="ETL_JOB", fund_id="BHMMF") as ctx:
                count = await _do_load(...)
                ctx.extra["loaded_rows"] = count
        """
        ctx = TimedContext()
        start = time.monotonic()
        try:
            yield ctx
        except Exception as e:
            ctx.status = "error"
            ctx.error = str(e)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            merged_extra = {**extra_kwargs, **ctx.extra}
            if ctx.error:
                merged_extra["error"] = ctx.error

            await self._write(
                db,
                level if ctx.status == "ok" else "ERROR",
                action,
                category=category,
                fund_id=fund_id,
                task_id=task_id,
                review_id=review_id,
                status=ctx.status,
                duration_ms=duration_ms,
                detail=ctx.error if ctx.error else None,
                extra=merged_extra,
            )

    # ─── HTTP 請求日誌（由 middleware 調用）─────────────────────

    async def log_http(
        self,
        db: AsyncSession,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int,
        actor: str = "unknown",
        fund_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        level = "INFO" if status_code < 400 else ("WARNING" if status_code < 500 else "ERROR")
        await self._write(
            db,
            level,
            f"{method} {path}",
            category="API_ACCESS",
            actor_override=actor,
            http_method=method,
            http_path=path,
            http_status=status_code,
            duration_ms=duration_ms,
            fund_id=fund_id,
            session_id=session_id,
            status="ok" if status_code < 400 else "error",
        )

    # ─── 核心寫入 ────────────────────────────────────────────────

    async def _write(
        self,
        db: AsyncSession,
        level: str,
        action: str,
        *,
        category: str = "SYSTEM",
        actor_override: str | None = None,
        fund_id: str | None = None,
        task_id: str | None = None,
        review_id: str | None = None,
        session_id: str | None = None,
        http_method: str | None = None,
        http_path: str | None = None,
        http_status: int | None = None,
        duration_ms: int | None = None,
        status: str = "ok",
        detail: str | None = None,
        extra: dict | None = None,
    ) -> None:
        actor = actor_override or self.actor
        extra_data = extra or {}

        # 1. 結構化控制台日誌（structlog → JSON）
        log_fn = getattr(self._slog, level.lower(), self._slog.info)
        log_fn(
            action,
            category=category, fund_id=fund_id, task_id=task_id,
            status=status, duration_ms=duration_ms, **extra_data,
        )

        # 2. 寫入 Postgres（非同步，忽略寫入失敗以免影響主流程）
        try:
            await db.execute(
                text("""
                    INSERT INTO fsi.op_logs (
                        level, category, actor, actor_type, action,
                        fund_id, task_id, review_id, session_id,
                        http_method, http_path, http_status, duration_ms,
                        status, detail, extra, service, host, version
                    ) VALUES (
                        :level, :category, :actor, :actor_type, :action,
                        :fund_id, :task_id, :review_id, :session_id,
                        :http_method, :http_path, :http_status, :duration_ms,
                        :status, :detail, :extra, :service, :host, :version
                    )
                """),
                {
                    "level": level, "category": category,
                    "actor": actor, "actor_type": self.actor_type, "action": action,
                    "fund_id": fund_id, "task_id": task_id,
                    "review_id": review_id, "session_id": session_id,
                    "http_method": http_method, "http_path": http_path,
                    "http_status": http_status, "duration_ms": duration_ms,
                    "status": status, "detail": detail,
                    "extra": json.dumps(extra_data, default=str),
                    "service": _SERVICE, "host": _HOST, "version": _VERSION,
                },
            )
            await db.commit()
        except Exception as e:
            # 日誌寫入失敗不能影響主業務邏輯
            std_log.error("op_log DB write failed", error=str(e), action=action)


# ── 模組級別快捷函數（不需要實例化）──────────────────────────────

_default_logger = OpLogger("fsi-platform")


async def log_event(
    db: AsyncSession,
    action: str,
    category: str,
    actor: str,
    actor_type: str = "system",
    level: str = "INFO",
    **kwargs: Any,
) -> None:
    """無需實例化 OpLogger 的快捷日誌函數。"""
    lg = OpLogger(actor, actor_type)
    await lg._write(db, level, action, category=category, **kwargs)
