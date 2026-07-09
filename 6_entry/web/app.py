"""Entry Layer — Web 入口（FastAPI）：Agent 模式 + 非 Agent 直接查詢。"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import agent_mode, agent_v2, direct_query, op_logs_ui, review_ui

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ARISK — Web Entry",
    description="統一入口：Agent 模式、Direct Query、人工審核收件箱。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent V2：SSE 流式 + tool_use + 多 Agent（整合 aiagent 模塊）
app.include_router(agent_v2.router, prefix="/agent/v2", tags=["Agent V2"])

# Agent V1（兼容舊版）
app.include_router(agent_mode.router, prefix="/agent", tags=["Agent V1"])

# Direct Query 路由：確定性計算，直接調用 Processing API
app.include_router(direct_query.router, prefix="/query", tags=["Direct Query"])

# 人工審核收件箱（含小富 AI）：審核員操作界面（代理到 Processing API）
app.include_router(review_ui.router, prefix="/review-ui", tags=["人工審核"])

# 操作日誌查看器
app.include_router(op_logs_ui.router, prefix="/logs-ui", tags=["操作日誌"])

# 靜態文件（Web UI）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "agent+direct"}
