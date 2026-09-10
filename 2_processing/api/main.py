"""Processing Layer FastAPI — 內部計算 API（供 Entry 層和 Agent 調用）。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .deps import get_db, verify_api_key
from .routers import agents, data_management, indicators, investment, op_logs, portfolio_cockpit, portfolio_opt, positions, quant, reports, review, risk, risk_rules, risk_testing, schedules, sql_assets, valuation


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在 ASGI worker 進程的生命週期內啟動調度器（避免 uvicorn reload 雙進程問題）
    from .routers.schedules import start_scheduler
    start_scheduler()
    yield

app = FastAPI(
    title="ARISK — Processing API",
    description="內部計算服務：持倉、風控、業績、人工審核。供 Entry 層和 Agent 調用，不直接暴露外網。",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(positions.router, prefix="/positions", tags=["持倉"])
app.include_router(data_management.router, prefix="/data-management", tags=["數據管理中心"])
app.include_router(indicators.router, prefix="/indicators", tags=["指標探索"])
app.include_router(valuation.router, prefix="/valuation", tags=["估值與損益"])
app.include_router(sql_assets.router, prefix="/sql-assets", tags=["SQL 資產庫"])
app.include_router(portfolio_cockpit.router, prefix="/portfolio-cockpit", tags=["組合駕駛艙"])
app.include_router(portfolio_opt.router, prefix="/portfolio-opt", tags=["組合優化"])
app.include_router(risk_testing.router, prefix="/risk-testing", tags=["專業風險測試"])
app.include_router(quant.router,     prefix="/quant",     tags=["Quant API"])
app.include_router(agents.router,    prefix="/agents",    tags=["Agent Interface"])
app.include_router(risk.router,      prefix="/risk",      tags=["風控"])
app.include_router(risk_rules.router, prefix="/risk-rules", tags=["風控規則配置"])
app.include_router(investment.router, prefix="/investment", tags=["投資風險分析"])
app.include_router(reports.router,   prefix="/reports",   tags=["報表生成"])
app.include_router(schedules.router, prefix="/schedules", tags=["定時報表"])
app.include_router(review.router,    prefix="/review",    tags=["人工審核"])
app.include_router(op_logs.router,   prefix="/op-logs",   tags=["操作日誌"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/context", dependencies=[Depends(verify_api_key)])
async def get_system_context(db: AsyncSession = Depends(get_db)):
    """返回系統上下文：在管基金列表 + 當前日期。供 Agent 動態獲取基礎信息。"""
    funds = []
    try:
        rows = await db.execute(text(
            "SELECT port_id, port_name FROM fsi.para_portfolio "
            "WHERE is_active = TRUE ORDER BY port_id"
        ))
        funds = [{"fund_id": r[0], "fund_name": r[1]} for r in rows.fetchall()]
    except Exception:
        await db.rollback()

    return {
        "current_date": date.today().isoformat(),
        "funds": funds,
        "note": "fund_id 用於所有工具調用的 fund_id 參數",
    }
