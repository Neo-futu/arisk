"""
platform_agent/engine/platform_runner.py — Platform Agent L1: 開發任務執行引擎

與 aiagent/engine/runner.py（業務 Agent）完全分離。
面向開發者，使用開發工具集（dev_tools.py）。

支持的開發 Agent 角色：
  architect  — 架構師（設計決策、技術選型）
  coder      — 代碼實現者（代碼生成、模式匹配）
  debugger   — 調試員（問題排查、服務診斷）
  reviewer   — 代碼審查員（質量、安全、一致性）
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator

from .system_tools import PLATFORM_TOOLS, execute_system_tool

logger = logging.getLogger(__name__)

AGENTS_DIR    = Path(__file__).parent.parent / "agents"
MAX_DEV_LOOPS = 8    # 開發任務工具調用上限

PLATFORM_AGENT_NAMES = {
    "scheduler":       "ARISK 系統調度員",
    "monitor":         "ARISK 系統監控員",
    "etl-coordinator": "ARISK ETL 協調員",
}

DEFAULT_DEV_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def _load_platform_prompt(agent_name: str) -> str:
    """載入 Platform Agent 的系統提示（agents/ + commons.md）。"""
    commons_path = AGENTS_DIR / "commons.md"
    agent_path   = AGENTS_DIR / f"{agent_name}.md"

    commons = ""
    if commons_path.exists():
        raw = commons_path.read_text(encoding="utf-8")
        commons = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()

    if not agent_path.exists():
        base = f"你是 ARISK 平台的 {PLATFORM_AGENT_NAMES.get(agent_name, '開發助手')}。"
    else:
        raw = agent_path.read_text(encoding="utf-8")
        base = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()

    return f"{base}\n\n---\n{commons}" if commons else base


async def run_platform_agent(
    messages:   list[dict],
    agent_name: str = "architect",
    model:      str | None = None,
) -> AsyncIterator[dict]:
    """
    Platform Agent 執行循環（async generator）。

    使用與 Chat Agent 相同的 ReAct 模式，但：
    - 使用開發工具集（dev_tools.py）
    - 面向開發者任務（代碼理解、架構設計、調試）
    - 系統提示來自 platform_agent/agents/
    """
    selected_model = model or DEFAULT_DEV_MODEL
    system = _load_platform_prompt(agent_name)

    # 僅支持 Anthropic（開發工具最適合 Claude）
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield {"type": "error", "message": "Platform Agent 需要設置 ANTHROPIC_API_KEY"}
        yield {"type": "done"}
        return

    try:
        import anthropic as _anthropic
    except ImportError:
        yield {"type": "error", "message": "請安裝 anthropic：pip install anthropic"}
        yield {"type": "done"}
        return

    client = _anthropic.Anthropic(api_key=api_key)
    working_messages = list(messages)
    loop_count = 0

    while loop_count < MAX_DEV_LOOPS:
        loop_count += 1
        try:
            response = client.messages.create(
                model=selected_model,
                system=system,
                messages=working_messages,
                tools=PLATFORM_TOOLS,
                max_tokens=4096,
            )
        except Exception as exc:
            err = str(exc)
            if "401" in err:
                yield {"type": "error", "message": "ANTHROPIC_API_KEY 無效（401）"}
            else:
                yield {"type": "error", "message": f"API 錯誤：{err[:200]}"}
            yield {"type": "done"}
            return

        assistant_content = []
        for block in response.content:
            if block.type == "text" and block.text.strip():
                yield {"type": "text", "content": block.text}
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })

        if response.stop_reason == "end_turn":
            yield {"type": "done"}
            return

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": assistant_content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                yield {"type": "tool_call", "name": block.name, "input": block.input, "id": block.id}
                result = await execute_system_tool(block.name, block.input)
                yield {"type": "tool_result", "name": block.name, "result": result, "id": block.id}
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            working_messages.append({"role": "user", "content": tool_results})

    yield {"type": "error", "message": f"超過最大循環輪次（{MAX_DEV_LOOPS}）"}
    yield {"type": "done"}
