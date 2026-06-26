"""內部數據 MCP Server — 只讀訪問 Postgres 持倉和風控結果。"""
from __future__ import annotations

import os
import json
from datetime import date

import asyncpg
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

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
                    "asset_type": {"type": "string", "description": "可選過濾：DEPOSIT/CD/CP/BOND"},
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
                },
                "required": ["fund_id", "start_date", "end_date"],
            },
        ),
        Tool(
            name="get_fund_list",
            description="查詢所有活躍基金列表。",
            inputSchema={"type": "object", "properties": {}},
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
        sql = "SELECT * FROM fsi.positions WHERE fund_id=$1 AND as_of_date=$2"
        params = [args["fund_id"], args["as_of_date"]]
        if args.get("asset_type"):
            sql += " AND asset_type=$3"
            params.append(args["asset_type"])
        sql += f" ORDER BY weight_pct DESC NULLS LAST LIMIT {args.get('limit', 50)}"
        rows = await conn.fetch(sql, *params)
        return {"positions": [dict(r) for r in rows], "count": len(rows)}

    elif name == "get_risk_snapshot":
        row = await conn.fetchrow(
            "SELECT * FROM fsi.risk_snapshots WHERE fund_id=$1 AND as_of_date=$2",
            args["fund_id"], args["as_of_date"],
        )
        return dict(row) if row else {}

    elif name == "get_nav_history":
        rows = await conn.fetch(
            "SELECT nav_date, nav_per_unit, total_nav FROM fsi.nav_history "
            "WHERE fund_id=$1 AND nav_date BETWEEN $2 AND $3 ORDER BY nav_date",
            args["fund_id"], args["start_date"], args["end_date"],
        )
        return {"nav": [dict(r) for r in rows]}

    elif name == "get_fund_list":
        rows = await conn.fetch("SELECT fund_id, fund_name, fund_type, base_currency FROM fsi.funds WHERE is_active")
        return {"funds": [dict(r) for r in rows]}

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
