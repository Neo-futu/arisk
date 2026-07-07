"""Processing Layer FastAPI — 內部計算 API（供 Entry 層和 Agent 調用）。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from .deps import get_db, verify_api_key
from .routers import op_logs, positions, review, risk

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="ARISK — Processing API",
    description="內部計算服務：持倉、風控、業績、人工審核。供 Entry 層和 Agent 調用，不直接暴露外網。",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(positions.router, prefix="/positions", tags=["持倉"])
app.include_router(risk.router,      prefix="/risk",      tags=["風控"])
app.include_router(review.router,    prefix="/review",    tags=["人工審核"])
app.include_router(op_logs.router,   prefix="/op-logs",   tags=["操作日誌"])


@app.get("/health")
async def health():
    return {"status": "ok"}
