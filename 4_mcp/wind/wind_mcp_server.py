"""WindAPI MCP Server — 封裝 Wind 數據為 MCP 工具。"""
from __future__ import annotations

import os
import logging
from datetime import date, datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

WIND_USERNAME = os.environ.get("WIND_USERNAME", "")
WIND_PASSWORD = os.environ.get("WIND_PASSWORD", "")

server = Server("wind-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="wind_get_price",
            description="取股票/債券/基金的歷史收盤價。",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "Wind 代碼列表，如 ['131810.SH']"},
                    "start_date": {"type": "string", "description": "開始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "結束日期 YYYY-MM-DD"},
                    "fields": {"type": "string", "description": "字段，默認 'close'", "default": "close"},
                },
                "required": ["codes", "start_date", "end_date"],
            },
        ),
        Tool(
            name="wind_get_fx",
            description="取外匯匯率歷史數據。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ccy_pair": {"type": "string", "description": "貨幣對，如 'USDCNY'"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["ccy_pair", "start_date", "end_date"],
            },
        ),
        Tool(
            name="wind_get_bond_info",
            description="取債券/CD/CP 基本信息（期限、票面、評級、發行人）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "fields": {
                        "type": "string",
                        "description": "字段列表，默認全部",
                        "default": "windcode,sec_name,issuer_name,carrydate,maturitydate,couponrate,rating,rating_inst",
                    },
                },
                "required": ["codes"],
            },
        ),
        Tool(
            name="wind_get_hibor",
            description="取 HIBOR 利率曲線數據。",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                    "tenors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "期限列表，如 ['ON','1W','1M','3M','6M','1Y']",
                    },
                },
                "required": ["date"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """調用 Wind API 並返回結果。"""
    try:
        result = await _dispatch_wind_call(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error("Wind MCP error [%s]: %s", name, e)
        return [TextContent(type="text", text=f"Error: {e}")]


async def _dispatch_wind_call(name: str, args: dict) -> str:
    """分發到具體 Wind API 調用。實際環境需安裝 WindPy 並連接 Wind 終端。"""
    if name == "wind_get_price":
        return _mock_price_response(args["codes"], args["start_date"], args["end_date"])
    elif name == "wind_get_fx":
        return _mock_fx_response(args["ccy_pair"], args["start_date"], args["end_date"])
    elif name == "wind_get_bond_info":
        return _mock_bond_info(args["codes"])
    elif name == "wind_get_hibor":
        return _mock_hibor(args["date"])
    else:
        return f"Unknown tool: {name}"


def _mock_price_response(codes: list, start: str, end: str) -> str:
    return f"[MOCK] Price data for {codes} from {start} to {end}. Install WindPy and connect Wind terminal for real data."


def _mock_fx_response(pair: str, start: str, end: str) -> str:
    rates = {"USDCNY": 7.25, "USDHKD": 7.78, "EURUSD": 1.09}
    pair_upper = pair.upper()
    rate = rates.get(pair_upper, 1.0)
    return f"[MOCK] {pair_upper}: {rate} (from {start} to {end})"


def _mock_bond_info(codes: list) -> str:
    return f"[MOCK] Bond info for {codes}. Connect Wind terminal for real data."


def _mock_hibor(dt: str) -> str:
    return f"[MOCK] HIBOR on {dt}: ON=5.1%, 1W=5.2%, 1M=5.3%, 3M=5.4%"


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
