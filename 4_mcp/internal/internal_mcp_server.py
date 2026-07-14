"""內部數據 MCP Server — 只讀訪問 Postgres 持倉和風控結果。"""
from __future__ import annotations

import os
import json
import importlib
from datetime import date, timedelta

import asyncpg
import numpy as np
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

_sql_queries = importlib.import_module("2_processing.tools.internal.sql_queries")
GET_FUND_LIST_SQL = _sql_queries.GET_FUND_LIST_SQL
GET_NAV_HISTORY_SQL = _sql_queries.GET_NAV_HISTORY_SQL
GET_RISK_SNAPSHOT_SQL = _sql_queries.GET_RISK_SNAPSHOT_SQL
GET_VAR_NAV_SERIES_SQL = _sql_queries.GET_VAR_NAV_SERIES_SQL
build_get_positions_query = _sql_queries.build_get_positions_query

try:
    from scipy.stats import norm
except Exception:  # pragma: no cover
    norm = None

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://fsi_user:change_me@localhost:5432/fsi_risk")

server = Server("fsi-internal-db")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_positions",
            description="查詢基金持倉（只讀）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "fund_id": {"type": "string"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "asset_type": {"type": "string", "description": "可選過濾：現金/定存/債券/回購等科目關鍵詞"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["fund_id", "as_of_date"],
            },
        ),
        Tool(
            name="get_risk_snapshot",
            description="查詢基金風控快照（WAM、WAL、合規狀態等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "fund_id": {"type": "string"},
                    "as_of_date": {"type": "string"},
                },
                "required": ["fund_id", "as_of_date"],
            },
        ),
        Tool(
            name="get_nav_history",
            description="查詢基金 NAV 歷史。",
            inputSchema={
                "type": "object",
                "properties": {
                    "fund_id": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "currency": {"type": "string", "default": "HKD"},
                },
                "required": ["fund_id", "start_date", "end_date"],
            },
        ),
        Tool(
            name="get_var_three_methods",
            description="基於 NAV 歷史直接計算 VaR 三方法（historical / monte_carlo / distribution）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "fund_id": {"type": "string"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "confidence": {"type": "number", "default": 0.99},
                    "horizon_days": {"type": "integer", "default": 1},
                    "lookback_days": {"type": "integer", "default": 252},
                    "min_observations": {"type": "integer", "default": 30},
                    "simulations": {"type": "integer", "default": 10000},
                    "currency": {"type": "string", "default": "HKD"},
                },
                "required": ["fund_id", "as_of_date"],
            },
        ),
        Tool(
            name="get_fund_list",
            description="查詢所有活躍基金列表。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_context",
            description="查詢系統上下文：當前日期 + 在管基金列表。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="query_business_db",
            description="只讀 SQL 查詢業務資料（僅允許 SELECT）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SELECT 查詢語句"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["sql"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await _dispatch(name, arguments, conn)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    finally:
        await conn.close()


async def _dispatch(name: str, args: dict, conn: asyncpg.Connection) -> dict:
    if name == "get_positions":
        sql, params = build_get_positions_query(
            fund_id=args["fund_id"],
            as_of_date=args["as_of_date"],
            asset_type=args.get("asset_type"),
            limit=args.get("limit", 50),
        )
        rows = await conn.fetch(sql, *params)
        return {"positions": [dict(r) for r in rows], "count": len(rows)}

    elif name == "get_risk_snapshot":
        row = await conn.fetchrow(GET_RISK_SNAPSHOT_SQL, args["fund_id"], args["as_of_date"])
        return dict(row) if row else {}

    elif name == "get_nav_history":
        rows = await conn.fetch(
            GET_NAV_HISTORY_SQL,
            args["fund_id"], args["start_date"], args["end_date"], args.get("currency", "HKD"),
        )
        return {"nav": [dict(r) for r in rows]}

    elif name == "get_var_three_methods":
        return await _compute_var_three_methods(conn, args)

    elif name == "get_fund_list":
        rows = await conn.fetch(GET_FUND_LIST_SQL)
        return {"funds": [dict(r) for r in rows]}

    elif name == "get_context":
        rows = await conn.fetch(GET_FUND_LIST_SQL)
        return {
            "current_date": date.today().isoformat(),
            "funds": [dict(r) for r in rows],
            "note": "fund_id 用於所有工具調用的 fund_id 參數",
        }

    elif name == "query_business_db":
        sql = str(args.get("sql", "")).strip().rstrip(";")
        limit = min(int(args.get("limit", 50)), 200)
        if not sql.upper().startswith("SELECT"):
            return {"error": "只允許 SELECT 查詢"}
        rows = await conn.fetch(f"{sql} LIMIT {limit}")
        return {"row_count": len(rows), "rows": [dict(r) for r in rows]}

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


async def _compute_var_three_methods(conn: asyncpg.Connection, args: dict) -> dict:
    fund_id = args["fund_id"]
    as_of_date = date.fromisoformat(args["as_of_date"])
    confidence = float(args.get("confidence", 0.99))
    horizon_days = int(args.get("horizon_days", 1))
    lookback_days = int(args.get("lookback_days", 252))
    min_observations = int(args.get("min_observations", 30))
    simulations = int(args.get("simulations", 10000))
    currency = args.get("currency", "HKD")

    start_date = as_of_date - timedelta(days=lookback_days * 2)
    rows = await conn.fetch(
        GET_VAR_NAV_SERIES_SQL,
        fund_id,
        start_date,
        as_of_date,
        currency,
    )
    if len(rows) < 2:
        return {
            "fund_id": fund_id,
            "as_of_date": as_of_date.isoformat(),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "results": [
                {"method": "INSUFFICIENT_DATA", "var_hkd": 0.0, "var_pct_nav": 0.0, "cvar_hkd": 0.0, "sample_size": 0},
                {"method": "INSUFFICIENT_DATA", "var_hkd": 0.0, "var_pct_nav": 0.0, "cvar_hkd": 0.0, "sample_size": 0},
                {"method": "INSUFFICIENT_DATA", "var_hkd": 0.0, "var_pct_nav": 0.0, "cvar_hkd": 0.0, "sample_size": 0},
            ],
        }

    navs = np.array([float(r["net_asset"]) for r in rows], dtype=float)
    returns = np.diff(navs) / navs[:-1]
    returns = returns[-lookback_days:]
    current_nav = float(navs[-1])

    if returns.size < min_observations:
        res = {"method": "INSUFFICIENT_DATA", "var_hkd": 0.0, "var_pct_nav": 0.0, "cvar_hkd": 0.0, "sample_size": 0}
        return {
            "fund_id": fund_id,
            "as_of_date": as_of_date.isoformat(),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "results": [res, res, res],
        }

    alpha = 1 - confidence

    # Historical
    hist_returns = returns * np.sqrt(horizon_days)
    hist_q = float(np.percentile(hist_returns, alpha * 100))
    hist_tail = hist_returns[hist_returns <= hist_q]
    hist_cvar = float(np.mean(hist_tail)) if hist_tail.size > 0 else hist_q
    historical = {
        "method": "HISTORICAL_SIMULATION",
        "var_hkd": abs(hist_q * current_nav),
        "var_pct_nav": abs(hist_q) * 100,
        "cvar_hkd": abs(hist_cvar * current_nav),
        "sample_size": int(returns.size),
    }

    # Monte Carlo
    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    if sigma <= 0:
        monte_carlo = {
            "method": "INSUFFICIENT_DATA",
            "var_hkd": 0.0,
            "var_pct_nav": 0.0,
            "cvar_hkd": 0.0,
            "sample_size": 0,
        }
        distribution = monte_carlo
    else:
        rng = np.random.default_rng(42)
        sim = rng.normal(mu * horizon_days, sigma * np.sqrt(horizon_days), simulations)
        mc_q = float(np.percentile(sim, alpha * 100))
        mc_tail = sim[sim <= mc_q]
        mc_cvar = float(np.mean(mc_tail)) if mc_tail.size > 0 else mc_q
        monte_carlo = {
            "method": "MONTE_CARLO",
            "var_hkd": abs(mc_q * current_nav),
            "var_pct_nav": abs(mc_q) * 100,
            "cvar_hkd": abs(mc_cvar * current_nav),
            "sample_size": simulations,
        }

        if norm is None:
            distribution = {
                "method": "INSUFFICIENT_DATA",
                "var_hkd": 0.0,
                "var_pct_nav": 0.0,
                "cvar_hkd": 0.0,
                "sample_size": 0,
            }
        else:
            z = float(norm.ppf(1 - confidence))
            d_var = -(mu * horizon_days + z * sigma * np.sqrt(horizon_days))
            d_cvar = -(mu * horizon_days - sigma * np.sqrt(horizon_days) * norm.pdf(z) / (1 - confidence))
            distribution = {
                "method": "DISTRIBUTION_FORMULA",
                "var_hkd": abs(d_var * current_nav),
                "var_pct_nav": abs(d_var) * 100,
                "cvar_hkd": abs(d_cvar * current_nav),
                "sample_size": int(returns.size),
            }

    return {
        "fund_id": fund_id,
        "as_of_date": as_of_date.isoformat(),
        "confidence": confidence,
        "horizon_days": horizon_days,
        "results": [historical, monte_carlo, distribution],
    }


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
