"""
aiagent/engine — ARISK AI Agent 執行引擎

模塊：
  tools.py   — FSI 業務工具定義（Claude tool_use 格式）+ 執行器
  runner.py  — tool_use 執行循環（agentic loop）
  stream.py  — SSE 流式輸出封裝
"""
from .runner import run_agent, load_agent_prompt, AGENT_NAMES
from .tools import TOOLS, execute_tool
from .stream import sse_generator

__all__ = [
    "run_agent",
    "load_agent_prompt",
    "AGENT_NAMES",
    "TOOLS",
    "execute_tool",
    "sse_generator",
]
