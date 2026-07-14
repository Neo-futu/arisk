"""Shared MCP client helpers for ARISK.

Launches local MCP servers over stdio and normalizes tool responses into dicts.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "").rstrip("/")

MCP_SERVER_SPECS: dict[str, dict[str, Any]] = {
    "internal": {
        "module": "4_mcp.internal.internal_mcp_server",
        "env_keys": ["DATABASE_URL"],
    },
    "wind": {
        "module": "4_mcp.wind.wind_mcp_server",
        "env_keys": ["WIND_USERNAME", "WIND_PASSWORD"],
    },
}


async def call_mcp_tool(server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a local MCP tool via stdio and normalize the response."""
    if MCP_GATEWAY_URL:
        gateway_result = await _call_via_gateway(server_name, tool_name, arguments or {})
        if not gateway_result.get("error"):
            return gateway_result
    return await _call_stdio_tool(server_name, tool_name, arguments)


async def _call_via_gateway(server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    url = f"{MCP_GATEWAY_URL}/mcp/{server_name}/{tool_name}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"arguments": arguments})
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:300], "server": server_name, "tool": tool_name}
        data = resp.json()
        return data if isinstance(data, dict) else {"content": data}
    except Exception as exc:
        return {"error": str(exc)[:300], "server": server_name, "tool": tool_name}


async def call_internal_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return await call_mcp_tool("internal", tool_name, arguments)


async def call_internal_tool_direct(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _call_stdio_tool("internal", tool_name, arguments)


async def call_wind_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return await call_mcp_tool("wind", tool_name, arguments)


async def call_wind_tool_direct(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _call_stdio_tool("wind", tool_name, arguments)


async def _call_stdio_tool(server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = MCP_SERVER_SPECS.get(server_name)
    if not spec:
        return {"error": f"未知 MCP 服務：{server_name}", "server": server_name, "tool": tool_name}

    env = os.environ.copy()
    for key in spec.get("env_keys", []):
        if key in os.environ:
            env[key] = os.environ[key]

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", spec["module"]],
        cwd=REPO_ROOT,
        env=env,
    )

    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments or {})
        return _normalize_response(response)
    except Exception as exc:
        logger.error("[mcp] %s.%s failed: %s", server_name, tool_name, exc)
        return {"error": str(exc)[:300], "server": server_name, "tool": tool_name}


def _normalize_response(response: Any) -> dict[str, Any]:
    content_items = getattr(response, "content", None)
    if not content_items:
        if isinstance(response, dict):
            return response
        return {"content": str(response)}

    text_parts: list[str] = []
    for item in content_items:
        text = getattr(item, "text", None)
        if text:
            text_parts.append(text)

    if not text_parts:
        return {"content": ""}

    text = "\n".join(text_parts).strip()
    if not text:
        return {"content": ""}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"content": parsed}
    except Exception:
        return {"content": text}