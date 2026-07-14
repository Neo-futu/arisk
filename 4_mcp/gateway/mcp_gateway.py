"""ARISK MCP Gateway.

This is a thin HTTP entry point that fans out to the local stdio MCP servers.
It lets aiagent/platform_agent talk to one place first, while the underlying
server calls remain split into internal/wind MCP servers.
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_client_mod = importlib.import_module("4_mcp.client")

app = FastAPI(title="ARISK MCP Gateway", version="0.1.0")


class MCPCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
async def tools() -> dict[str, list[str]]:
    return {
        "internal": [
            "get_context",
            "get_fund_list",
            "get_positions",
            "get_risk_snapshot",
            "get_nav_history",
            "get_var_three_methods",
            "query_business_db",
        ],
        "wind": [
            "wind_get_price",
            "wind_get_fx",
            "wind_get_bond_info",
            "wind_get_index_components",
            "wind_get_yield_curve",
        ],
    }


@app.post("/mcp/{server_name}/{tool_name}")
async def call_tool(server_name: str, tool_name: str, body: MCPCallRequest) -> dict[str, Any]:
    if server_name == "internal":
        return await _client_mod.call_internal_tool_direct(tool_name, body.arguments)
    if server_name == "wind":
        return await _client_mod.call_wind_tool_direct(tool_name, body.arguments)
    raise HTTPException(status_code=404, detail=f"Unknown MCP server: {server_name}")


def main() -> None:
    import uvicorn

    port = int(os.getenv("MCP_GATEWAY_PORT", "8002"))
    uvicorn.run("4_mcp.gateway.mcp_gateway:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()