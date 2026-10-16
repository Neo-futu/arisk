"""
aiagent/engine/runner.py — 多模型 tool_use 執行循環

支持的 Provider：
  - Anthropic Claude（默認）：claude-sonnet-4-6 / claude-opus-4-5 / claude-haiku-4-5
  - OpenAI GPT（可選）：gpt-4o / gpt-4o-mini / gpt-4-turbo（需設置 OPENAI_API_KEY）

Provider 選擇邏輯：
  - 根據 model 名稱前綴自動識別（"gpt-" → OpenAI，其餘 → Anthropic）
  - 或由調用方顯式傳入 provider 參數

執行流程：
  1. 載入 agents/{name}.md 系統提示
  2. 調用對應 Provider API（with tools）
  3. tool_use → 執行工具 → 追加結果 → 繼續循環（最多 10 輪）
  4. 直到 end_turn → yield done
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv

from .tools import TOOLS, execute_tool

_ROOT = Path(__file__).resolve().parents[2]  # arisk/
load_dotenv(_ROOT / ".env", override=False)
load_dotenv(override=False)
logger = logging.getLogger(__name__)

# ── 路徑 ──────────────────────────────────────────────────────────
AGENTS_DIR    = Path(__file__).parent.parent / "agents"
MAX_TOOL_LOOPS = 10
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# ── 可用 Agent 名稱 ───────────────────────────────────────────────
AGENT_NAMES = {
    "general":            "通用助理",
    "risk-analyst":       "ARISK 風控分析師",
    "compliance-officer": "SFC 合規審查員",
    "fund-reporter":      "基金報表助理",
    "market-researcher":  "市場研究員",
    "gl-reconciler":      "基金 GL 對賬員",
    "kyc-screener":       "KYC 合規篩查員",
    "statement-auditor":  "NAV 報表審計員",
    "valuation-reviewer": "組合估值審查員",
    "month-end-closer":   "月末結賬助手",
}

# ── 支持的模型（Provider 自動判斷） ──────────────────────────────
SUPPORTED_MODELS = {
    # Anthropic Claude — 默認 Provider
    "claude-sonnet-4-6":           {"provider": "anthropic", "label": "Claude Sonnet 4.6（推薦）"},
    "claude-opus-4-5":             {"provider": "anthropic", "label": "Claude Opus 4.5（最強）"},
    "claude-haiku-4-5-20251001":   {"provider": "anthropic", "label": "Claude Haiku 4.5（最快）"},
    # OpenAI GPT — 需設置 OPENAI_API_KEY
    "gpt-4o":                      {"provider": "openai",    "label": "GPT-4o（OpenAI）"},
    "gpt-4o-mini":                 {"provider": "openai",    "label": "GPT-4o Mini（OpenAI）"},
    # Google Gemini — 需設置 GEMINI_API_KEY（香港 API 可用）
    "gemini-2.0-flash":            {"provider": "gemini",    "label": "Gemini 2.0 Flash（Google，推薦）"},
    "gemini-1.5-pro":              {"provider": "gemini",    "label": "Gemini 1.5 Pro（Google）"},
    "gemini-1.5-flash":            {"provider": "gemini",    "label": "Gemini 1.5 Flash（Google，最快）"},
    # 國產大模型 — OpenAI 兼容接口
    # Kimi（月之暗面）— 需設置 MOONSHOT_API_KEY，API: api.moonshot.cn
    "moonshot-v1-32k":             {"provider": "moonshot",  "label": "Kimi moonshot-v1-32k（推薦）",
                                    "base_url": "https://api.moonshot.cn/v1"},
    "moonshot-v1-128k":            {"provider": "moonshot",  "label": "Kimi moonshot-v1-128k（長文）",
                                    "base_url": "https://api.moonshot.cn/v1"},
    # DeepSeek（深度求索）— 需設置 DEEPSEEK_API_KEY，API: api.deepseek.com
    "deepseek-chat":               {"provider": "deepseek",  "label": "DeepSeek Chat（V3，推薦）",
                                    "base_url": "https://api.deepseek.com/v1"},
    "deepseek-reasoner":           {"provider": "deepseek",  "label": "DeepSeek R1（推理增強）",
                                    "base_url": "https://api.deepseek.com/v1"},
    # OpenRouter（sk-or-v1-...）— 与 Cursor「Override OpenAI Base URL」常用同一类 Key；可与 OPENAI_API_KEY 并行
    "x-ai/grok-4.20":              {"provider": "openrouter", "label": "xAI Grok 4.20（OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "x-ai/grok-4.3":               {"provider": "openrouter", "label": "xAI Grok 4.3（OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "anthropic/claude-sonnet-4":   {"provider": "openrouter", "label": "Claude Sonnet 4（via OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "anthropic/claude-opus-4":     {"provider": "openrouter", "label": "Claude Opus 4（via OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "openai/gpt-4o":               {"provider": "openrouter", "label": "GPT-4o（via OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "openai/gpt-4o-mini":          {"provider": "openrouter", "label": "GPT-4o Mini（via OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    "google/gemini-2.0-flash-001": {"provider": "openrouter", "label": "Gemini 2.0 Flash（via OpenRouter）",
                                    "base_url": _OPENROUTER_BASE},
    # Cursor Agent SDK（Ask AI / Agent Chat）
    # 步骤：CURSOR_API_KEY → ModelSelection → 可选 tools 预取(MCP/HTTP) → bridge(cwd=arisk) → 纯文本回答
    # Ask AI 默认禁用本地 shell/读写工具，避免误改仓库；Composer 2.5 比 Auto Router 更稳
    "auto-smart":                  {"provider": "cursor", "label": "Cursor Auto（Router）"},
    "composer-2.5":                {"provider": "cursor", "label": "Cursor Composer 2.5"},
}

def _resolve_default_model() -> str:
    """有 CURSOR_API_KEY 时优先 Cursor；否则 Anthropic。"""
    if os.getenv("CURSOR_API_KEY", "").strip():
        return os.getenv("CURSOR_MODEL", "auto-smart").strip() or "auto-smart"
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


DEFAULT_MODEL = _resolve_default_model()


def detect_provider(model: str) -> str:
    """根據模型名稱前綴自動識別 Provider。"""
    # 先查表（OpenRouter 的 openai/gpt-4o 不能誤判為直連 OpenAI）
    info = SUPPORTED_MODELS.get(model, {})
    if info.get("provider"):
        return str(info["provider"])
    if model in {"auto-smart", "auto", "composer-2.5", "composer-2"} or model.startswith("composer-"):
        return "cursor"
    if "/" in model:
        return "openrouter"
    if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
        return "openai"
    if model.startswith("gemini-"):
        return "gemini"
    if model.startswith("moonshot-"):
        return "moonshot"
    if model.startswith("deepseek-"):
        return "deepseek"
    if model.startswith("x-ai/") or model.startswith("grok"):
        return "openrouter"
    return "anthropic"


# ── 工具格式轉換（Anthropic ↔ OpenAI） ──────────────────────────
def _tools_for_openai(tools: list[dict]) -> list[dict]:
    """將 Anthropic tool_use 格式轉換為 OpenAI function_calling 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in tools
    ]


# ── Anthropic 執行 ────────────────────────────────────────────────
async def _run_anthropic(
    messages: list[dict],
    system: str,
    model: str,
    stream_callback,
    extra_tools: list[dict] | None = None,
) -> None:
    """Anthropic Claude tool_use 循環。"""
    try:
        import anthropic as _anthropic
    except ImportError:
        await stream_callback({"type": "error", "message": "請安裝 anthropic：pip install anthropic"})
        return

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        await stream_callback({
            "type": "error",
            "message": (
                "未設置 ANTHROPIC_API_KEY。\n"
                "請前往 https://console.anthropic.com/settings/keys 創建 Key，\n"
                "並填入 .env：ANTHROPIC_API_KEY=sk-ant-api03-..."
            ),
        })
        return

    client = _anthropic.Anthropic(api_key=key)
    working_messages = list(messages)
    loop_count = 0
    effective_tools = extra_tools if extra_tools else TOOLS

    while loop_count < MAX_TOOL_LOOPS:
        loop_count += 1
        try:
            response = client.messages.create(
                model=model,
                system=system,
                messages=working_messages,
                tools=effective_tools,
                max_tokens=4096,
            )
        except Exception as exc:
            err = str(exc)
            if "401" in err or "invalid secret key" in err or "Auth error" in err:
                await stream_callback({
                    "type": "error",
                    "message": "Claude API 認證失敗（401）。請確認 .env 中 ANTHROPIC_API_KEY 有效。",
                })
            elif "529" in err or "overloaded" in err.lower():
                await stream_callback({"type": "error", "message": "Claude API 服務繁忙（529），請稍後重試。"})
            else:
                await stream_callback({"type": "error", "message": f"Claude API 錯誤：{err[:200]}"})
            return

        assistant_content = []
        for block in response.content:
            if block.type == "text" and block.text.strip():
                await stream_callback({"type": "text", "content": block.text})
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })

        if response.stop_reason == "end_turn":
            return

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": assistant_content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                await stream_callback({"type": "tool_call", "name": block.name, "input": block.input, "id": block.id})
                result = await execute_tool(block.name, block.input)
                await stream_callback({"type": "tool_result", "name": block.name, "result": result, "id": block.id})
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            working_messages.append({"role": "user", "content": tool_results})

    await stream_callback({"type": "error", "message": f"超過最大工具循環輪次（{MAX_TOOL_LOOPS}）"})


# Ask AI / Chat 禁用 Cursor 本地工具，避免 Agent 误改仓库或生成坏 JS（Missing initializer…）
_CURSOR_CHAT_DISALLOWED_TOOLS = (
    "shell",
    "edit",
    "delete",
    "read",
    "grep",
    "glob",
    "ls",
    "task",
    "piBash",
    "piEdit",
    "piWrite",
    "piRead",
    "piFind",
    "piGrep",
    "piLs",
    "mcp",
    "fetch",
    "webSearch",
    "webFetch",
    "semSearch",
    "applyAgentDiff",
    "createAgent",
    "createPlan",
    "computerUse",
    "writeCanvas",
    "writeShellStdin",
)


def _cursor_model_selection(model: str):
    """Build Cursor SDK model selection（统一返回 ModelSelection）。"""
    from cursor_sdk import ModelParameterValue, ModelSelection

    selected = (model or "").strip() or "auto-smart"
    if selected in {"auto", "auto-smart", "default"}:
        mode = os.getenv("CURSOR_OPTIMIZE_FOR", "balanced").strip() or "balanced"
        return ModelSelection(
            id="auto-smart",
            params=[ModelParameterValue(id="optimize_for", value=mode)],
        )
    # composer-2 / composer-2.5 等：显式 ModelSelection，避免字符串路径偶发 internal 错
    return ModelSelection(id=selected)


def _msg_text(content: object) -> str:
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def _resolve_fund_id(text: str, context: dict | None) -> str:
    """从 context / 用户话术解析 fund_id；兼容 BMM001 → BHMMF001。"""
    fund_id = str((context or {}).get("fund_id") or "").strip().upper()
    if fund_id:
        return fund_id
    m = re.search(r"\b(BHMMF\d{3}|BHMF\d{3}|BMM\d{3})\b", text or "", re.I)
    if not m:
        return ""
    raw = m.group(1).upper()
    if raw.startswith("BHMMF"):
        return raw
    num = re.search(r"\d+", raw)
    return f"BHMMF{num.group(0).zfill(3)}" if num else raw


def _build_cursor_prompt(system: str, messages: list[dict], tool_bundle: str = "") -> str:
    parts = [
        "你是 ARISK Ask AI / 风控助手。这是一次对话问答，不是代码改造任务。",
        "规则：",
        "1. 只输出对用户的文字回答（可用 Markdown）。禁止输出或执行任何代码。",
        "2. 不要探索、搜索、修改任何文件，不要运行 shell/命令，不要调用工具。",
        "3. 下方【工具预取结果】或用户消息里的 Page context / Risk Metrics 来自真实系统，必须优先使用；禁止编造 NAV/VaR/持仓。",
        "4. 若上下文已有基金列表、持仓或 VaR，直接据此回答；仅当明确缺失时才说明缺数据。",
        "",
        "【系统提示】",
        system.strip(),
        "",
    ]
    if tool_bundle.strip():
        parts.extend(["【工具预取结果】", tool_bundle.strip(), ""])
    parts.append("【对话】")
    for msg in messages:
        role = msg.get("role", "user")
        parts.append(f"{role}: {_msg_text(msg.get('content', ''))}")
    parts.append("")
    parts.append("请直接回答最后一条 user 消息（纯文字/Markdown，不要写代码）。")
    return "\n".join(parts)


async def _prefetch_tools_for_cursor(
    messages: list[dict],
    context: dict | None,
    stream_callback,
) -> str:
    """Cursor SDK 无 native tool_use：调 LLM 前走 arisk Layer3 tools（MCP→processing）。"""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = _msg_text(m.get("content", ""))
            break

    # Ask AI / Copilot 已把 Page context / Risk Metrics 注入用户消息时，跳过二次预取，
    # 避免 Cursor Auto 在工具+长上下文下长时间卡住。
    embedded_markers = (
        "Page context:",
        "Risk Metrics",
        "var_compare",
        "组合摘要",
        "【工具预取结果】",
    )
    if any(marker in last_user for marker in embedded_markers):
        return ""

    text_l = last_user.lower()
    fund_id = _resolve_fund_id(last_user, context)
    as_of = str((context or {}).get("as_of_date") or "").strip()

    wants_funds = any(k in text_l for k in (
        "基金", "fund", "有哪些", "列表", "portfolio", "在管",
    ))
    wants_pos = any(k in text_l for k in (
        "持仓", "持倉", "position", "构成", "構成", "明细", "明細", "allocation", "配置",
    ))
    wants_var = any(k in text_l for k in (
        "var", "风险", "風險", "wam", "wal", "exposure", "暴露",
    ))
    # 有基金上下文时，数据类问题默认拉持仓，避免空答
    if fund_id and not (wants_funds or wants_pos or wants_var):
        wants_pos = any(k in text_l for k in ("多少", "怎样", "怎麼", "如何", "分析", "看看", "查询", "查詢"))

    calls: list[tuple[str, dict]] = []
    if wants_funds or not fund_id:
        calls.append(("get_system_info", {}))
    if fund_id and (wants_pos or wants_var):
        if not as_of:
            # 先拉 system_info 拿默认估值日
            if not any(n == "get_system_info" for n, _ in calls):
                calls.insert(0, ("get_system_info", {}))
        if wants_pos:
            calls.append(("get_positions", {
                "fund_id": fund_id,
                "as_of_date": as_of or "",  # 后面用 system_info 补
                "limit": 50,
            }))
        if wants_var:
            calls.append(("get_var_compare", {
                "fund_id": fund_id,
                "as_of_date": as_of or "",
            }))

    if not calls:
        # 兜底：至少给基金列表，避免 Cursor 空上下文瞎答
        calls.append(("get_system_info", {}))

    chunks: list[str] = []
    sys_info: dict = {}
    for idx, (name, inp) in enumerate(calls):
        call_id = f"cursor-prefetch-{idx}-{name}"
        if name in {"get_positions", "get_var_compare"} and not inp.get("as_of_date"):
            as_of = (
                str(sys_info.get("as_of_date") or sys_info.get("current_date") or as_of or "")
            )
            if not as_of:
                from datetime import date as _date
                as_of = _date.today().isoformat()
            inp = {**inp, "as_of_date": as_of}
        try:
            await stream_callback({
                "type": "tool_call", "name": name, "input": inp, "id": call_id,
            })
            result = await execute_tool(name, inp)
            if name == "get_system_info" and isinstance(result, dict):
                sys_info = result
                # 若用户只说「1号基金」等，尝试从列表解析
                if not fund_id:
                    funds = result.get("funds") or result.get("fund_list") or []
                    if isinstance(funds, list) and funds:
                        first = funds[0]
                        if isinstance(first, dict):
                            fund_id = str(first.get("fund_id") or first.get("id") or "")
                        elif isinstance(first, str):
                            fund_id = first
            await stream_callback({
                "type": "tool_result", "name": name, "result": result, "id": call_id,
            })
            chunks.append(
                f"### {name}\n```json\n{json.dumps(result, ensure_ascii=False, default=str)[:6000]}\n```"
            )
        except Exception as exc:
            err = {"error": str(exc)[:200], "tool": name}
            await stream_callback({
                "type": "tool_result", "name": name, "result": err, "id": call_id,
            })
            chunks.append(f"### {name}\n```json\n{json.dumps(err, ensure_ascii=False)}\n```")

    return "\n\n".join(chunks)


def _format_cursor_error(exc: BaseException) -> str:
    """Cursor 异常有时 str(exc) 为空，需拼 message/code/cause。"""
    chunks: list[str] = []
    message = getattr(exc, "message", None) or str(exc)
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    if code:
        chunks.append(str(code))
    if status:
        chunks.append(f"HTTP {status}")
    if message:
        chunks.append(str(message))
    if request_id:
        chunks.append(f"request_id={request_id}")
    if not chunks:
        chunks.append(repr(exc))
    cause = getattr(exc, "cause", None) or getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        chunks.append(f"cause={_format_cursor_error(cause)}")
    elif cause:
        chunks.append(f"cause={cause}")
    return " | ".join(chunks)[:500]


def _cursor_invoke_in_fresh_loop(prompt: str, model: str, api_key: str) -> tuple[str, str]:
    """在独立事件循环中执行 Cursor Agent。

    uvicorn/Windows 默认循环常无法 spawn subprocess（NotImplementedError），
    因此放到线程内 asyncio.run（ProactorEventLoop）执行。

    cwd 必须是 arisk git 根（空临时目录会导致 bridge/prompt 挂起）。
    禁用本地读写/shell 工具，避免 Agent 误改仓库或触发
    internal「Missing initializer in const declaration」。
    """
    from cursor_sdk import AgentOptions, LocalAgentOptions
    from cursor_sdk.asyncio import AsyncAgent, AsyncClient

    workspace = str(_ROOT)

    async def _inner() -> tuple[str, str]:
        options = AgentOptions(
            api_key=api_key,
            model=_cursor_model_selection(model),
            local=LocalAgentOptions(cwd=workspace, setting_sources=[]),
            disallowed_tools=list(_CURSOR_CHAT_DISALLOWED_TOOLS),
        )
        async with await AsyncClient.launch_bridge(workspace=workspace) as client:
            result = await AsyncAgent.prompt(prompt, options, client=client)
        status = str(getattr(result, "status", "") or "")
        text = str(getattr(result, "result", None) or "").strip()
        return status, text

    return asyncio.run(_inner())


async def _run_cursor(
    messages: list[dict],
    system: str,
    model: str,
    stream_callback,
    context: dict | None = None,
) -> None:
    """Cursor Agent SDK one-shot；先走 arisk tools→MCP/processing 预取，再调 Cursor LLM。"""
    key = os.getenv("CURSOR_API_KEY", "").strip()
    if not key:
        await stream_callback({
            "type": "error",
            "message": (
                "未设置 CURSOR_API_KEY。\n"
                "请到 https://cursor.com/dashboard 创建 API Key（crsr_...），\n"
                "并写入 .env：CURSOR_API_KEY=crsr_..."
            ),
        })
        return

    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        await stream_callback({
            "type": "error",
            "message": "请安装 cursor-sdk：pip install cursor-sdk",
        })
        return

    # Layer 3：与 Anthropic/OpenAI 同一套 tools，Cursor 无 native tool_use 故预取注入
    tool_bundle = await _prefetch_tools_for_cursor(messages, context, stream_callback)

    selected = model or os.getenv("CURSOR_MODEL", "auto-smart").strip() or "auto-smart"
    prompt = _build_cursor_prompt(system, messages, tool_bundle=tool_bundle)
    # Ask AI 浮窗场景默认更短超时，避免 UI 长期停在「思考中」
    timeout_s = float(os.getenv("CURSOR_CHAT_TIMEOUT_SEC", "75"))

    try:
        status, text = await asyncio.wait_for(
            asyncio.to_thread(_cursor_invoke_in_fresh_loop, prompt, selected, key),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        await stream_callback({
            "type": "error",
            "message": (
                f"Cursor Agent 超时（>{int(timeout_s)}s）。"
                "请换选 Composer 2.5，或检查本机是否有卡住的 cursor-sdk-bridge 进程。"
            ),
        })
        return
    except Exception as exc:
        err = _format_cursor_error(exc)
        if "NotImplementedError" in err or isinstance(exc, NotImplementedError):
            await stream_callback({
                "type": "error",
                "message": (
                    "Cursor Agent 在当前服务事件循环下无法启动 bridge（Windows NotImplementedError）。"
                    "请确认已使用最新 runner（线程隔离），并重启 backend-unified。"
                ),
            })
        elif "401" in err or "auth" in err.lower() or "unauthorized" in err.lower():
            await stream_callback({
                "type": "error",
                "message": "Cursor API 认证失败。请确认 .env 中 CURSOR_API_KEY 有效。",
            })
        elif "Missing initializer" in err or "const declaration" in err:
            await stream_callback({
                "type": "error",
                "message": (
                    "Cursor Agent 内部错误（工具/工作区解析失败）。"
                    "已切换为隔离问答模式；请重试一次。若仍失败，可改选 OpenAI 模型。"
                ),
            })
        else:
            await stream_callback({"type": "error", "message": f"Cursor Agent 错误：{err}"})
        return

    if text:
        await stream_callback({"type": "text", "content": text})
    else:
        await stream_callback({
            "type": "error",
            "message": f"Cursor Agent 未返回文本结果（status={status or 'unknown'}）。可改选 Composer 2.5 重试。",
        })


# ── OpenAI 執行 ───────────────────────────────────────────────────
async def _run_openai(
    messages: list[dict],
    system: str,
    model: str,
    stream_callback,
    base_url: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
    provider_label: str = "OpenAI",
    extra_tools: list[dict] | None = None,
) -> None:
    """
    OpenAI-compatible API function_calling 循環。
    兼容 OpenAI / Kimi（月之暗面）/ DeepSeek 等使用相同協議的服務。

    base_url     : 自定義 API 端點（None = 使用 OpenAI 官方）
    api_key_env  : 讀取 API Key 的環境變量名
    provider_label: 錯誤信息中顯示的 Provider 名稱
    """
    try:
        import openai as _openai
    except ImportError:
        await stream_callback({"type": "error", "message": "請安裝 openai：pip install openai"})
        return

    key = os.getenv(api_key_env, "")
    if not key:
        await stream_callback({
            "type": "error",
            "message": f"未設置 {api_key_env}。請在 .env 中添加：{api_key_env}=sk-...",
        })
        return

    client = _openai.AsyncOpenAI(api_key=key, base_url=base_url) if base_url else _openai.AsyncOpenAI(api_key=key)
    oai_messages = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": m["content"]} for m in messages
    ]
    oai_tools = _tools_for_openai(extra_tools if extra_tools else TOOLS)
    loop_count = 0

    while loop_count < MAX_TOOL_LOOPS:
        loop_count += 1
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=oai_messages,
                tools=oai_tools,
                tool_choice="auto",
                max_tokens=4096,
            )
        except Exception as exc:
            err = str(exc)
            if "401" in err or "incorrect api key" in err.lower() or "invalid api key" in err.lower():
                await stream_callback({"type": "error", "message": f"{provider_label} API Key 無效（401）。請確認 {api_key_env}。"})
            else:
                await stream_callback({"type": "error", "message": f"{provider_label} API 錯誤：{err[:200]}"})
            return

        choice   = response.choices[0]
        msg      = choice.message
        finish   = choice.finish_reason

        if msg.content:
            await stream_callback({"type": "text", "content": msg.content})

        if finish == "stop":
            return

        if finish == "tool_calls" and msg.tool_calls:
            oai_messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})
            for tc in msg.tool_calls:
                try:
                    inp = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    inp = {}
                await stream_callback({"type": "tool_call", "name": tc.function.name, "input": inp, "id": tc.id})
                result = await execute_tool(tc.function.name, inp)
                await stream_callback({"type": "tool_result", "name": tc.function.name, "result": result, "id": tc.id})
                oai_messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

    await stream_callback({"type": "error", "message": f"超過最大循環輪次（{MAX_TOOL_LOOPS}）"})


# ── Google Gemini 執行 ───────────────────────────────────────────
async def _run_gemini(
    messages: list[dict],
    system: str,
    model: str,
    stream_callback,
) -> None:
    """Google Gemini function_calling 循環（使用 google-generativeai SDK）。"""
    try:
        import google.generativeai as genai
    except ImportError:
        await stream_callback({
            "type": "error",
            "message": "請安裝 google-generativeai：pip install google-generativeai"
        })
        return

    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        await stream_callback({
            "type": "error",
            "message": (
                "未設置 GEMINI_API_KEY。\n"
                "請前往 https://aistudio.google.com/apikey 創建 Key，\n"
                "並填入 .env：GEMINI_API_KEY=AIza..."
            ),
        })
        return

    genai.configure(api_key=key)

    # 將 Anthropic tool 格式轉為 Gemini FunctionDeclaration
    def _to_gemini_tools():
        from google.generativeai.types import FunctionDeclaration, Tool as GeminiTool
        decls = [
            FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["input_schema"],
            )
            for t in TOOLS
        ]
        return [GeminiTool(function_declarations=decls)]

    # 構建對話歷史（Gemini 格式）
    gemini_history = []
    for m in messages[:-1]:   # 最後一條作為 prompt 傳入
        role = "user" if m["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [m["content"]]})

    user_msg = messages[-1]["content"] if messages else ""

    try:
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
            tools=_to_gemini_tools(),
        )
        chat = gemini_model.start_chat(history=gemini_history)
    except Exception as exc:
        await stream_callback({"type": "error", "message": f"Gemini 初始化失敗：{exc}"})
        return

    loop_count = 0
    current_msg = user_msg

    while loop_count < MAX_TOOL_LOOPS:
        loop_count += 1
        try:
            response = chat.send_message(current_msg)
        except Exception as exc:
            err = str(exc)
            if "API_KEY" in err or "api key" in err.lower() or "401" in err:
                await stream_callback({
                    "type": "error",
                    "message": "Gemini API Key 無效。請確認 GEMINI_API_KEY 已正確設置。"
                })
            else:
                await stream_callback({"type": "error", "message": f"Gemini API 錯誤：{err[:200]}"})
            return

        tool_calls_found = False
        tool_results_parts = []

        for part in response.parts:
            # 文字輸出
            if hasattr(part, "text") and part.text:
                await stream_callback({"type": "text", "content": part.text})

            # Function call（Gemini 的 tool_use）
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                tool_calls_found = True
                inp = dict(fc.args) if fc.args else {}
                call_id = f"gemini_{loop_count}_{fc.name}"

                await stream_callback({"type": "tool_call", "name": fc.name, "input": inp, "id": call_id})
                result = await execute_tool(fc.name, inp)
                await stream_callback({"type": "tool_result", "name": fc.name, "result": result, "id": call_id})

                # 構建 function_response
                from google.generativeai.types import protos
                tool_results_parts.append(
                    protos.Part(function_response=protos.FunctionResponse(
                        name=fc.name,
                        response={"result": json.dumps(result, ensure_ascii=False, default=str)},
                    ))
                )

        if tool_calls_found and tool_results_parts:
            # 把工具結果發回繼續循環
            current_msg = tool_results_parts
        else:
            return  # 沒有 tool call，結束

    await stream_callback({"type": "error", "message": f"超過最大循環輪次（{MAX_TOOL_LOOPS}）"})


# ── 主入口 ────────────────────────────────────────────────────────
def _load_commons() -> str:
    """載入 commons.md 公共上下文，注入所有 agent。"""
    commons_path = AGENTS_DIR / "commons.md"
    if not commons_path.exists():
        return ""
    text = commons_path.read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def load_agent_prompt(agent_name: str) -> str:
    commons = _load_commons()
    md_path = AGENTS_DIR / f"{agent_name}.md"
    if not md_path.exists():
        agent_prompt = (
            f"你是 ARISK 平台的 {AGENT_NAMES.get(agent_name, 'AI 助手')}。\n"
            "可用工具：get_system_info, get_exposure, get_var, get_var_compare, "
            "get_positions, get_nav_history, sector_overview"
        )
    else:
        raw = md_path.read_text(encoding="utf-8")
        agent_prompt = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()

    if commons:
        return f"{agent_prompt}\n\n---\n{commons}"
    return agent_prompt


async def _load_user_custom_tools(user_id: str) -> list[dict]:
    """
    從 iam.user_custom_tool 加載用戶個人工具，
    動態追加到 LLM 的 tool_use 聲明中。
    """
    try:
        import asyncpg
        import json as _json
        db_url = os.getenv("DATABASE_URL") or (
            f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
            f"{os.getenv('POSTGRES_PASSWORD','postgres')}@"
            f"{os.getenv('POSTGRES_SERVER','localhost')}:"
            f"{os.getenv('POSTGRES_PORT','5432')}/"
            f"{os.getenv('POSTGRES_DB','fsi_risk')}"
        )
        conn = await asyncpg.connect(db_url)
        rows = await conn.fetch(
            """SELECT tool_name, display_name, description, endpoint, method, parameters
               FROM iam.user_custom_tool
               WHERE user_id = $1::uuid AND enabled = true
               ORDER BY created_at""",
            user_id,
        )
        await conn.close()
        tools = []
        for r in rows:
            try:
                params = _json.loads(r["parameters"] or "{}")
            except Exception:
                params = {}
            tools.append({
                "name":         r["tool_name"],
                "description":  f"[用戶自定義工具] {r['display_name']}: {r['description']}",
                "input_schema": params if params.get("type") == "object" else {
                    "type": "object", "properties": params, "required": []
                },
                "_user_tool":   True,
                "_endpoint":    r["endpoint"],
                "_method":      r["method"],
            })
        return tools
    except Exception as exc:
        logger.debug("[runner] load_user_custom_tools failed: %s", exc)
        return []


async def _load_user_agent_config(user_id: str) -> dict:
    """
    從 iam.user_agent_config 加載用戶專屬 Agent 配置。
    不存在或 DB 不可用時返回空 dict（使用系統默認值）。
    """
    try:
        import asyncpg
        db_url = os.getenv("DATABASE_URL") or (
            f"postgresql://{os.getenv('POSTGRES_USER','postgres')}:"
            f"{os.getenv('POSTGRES_PASSWORD','postgres')}@"
            f"{os.getenv('POSTGRES_SERVER','localhost')}:"
            f"{os.getenv('POSTGRES_PORT','5432')}/"
            f"{os.getenv('POSTGRES_DB','fsi_risk')}"
        )
        conn = await asyncpg.connect(db_url)
        row = await conn.fetchrow(
            """SELECT default_agent_id, default_model_id, custom_instructions,
                      tools_enabled, memory_enabled, rag_enabled, max_context_turns,
                      agent_name
               FROM iam.user_agent_config WHERE user_id = $1::uuid""",
            user_id,
        )
        await conn.close()
        return dict(row) if row else {}
    except Exception as exc:
        logger.debug("[runner] load_user_agent_config failed: %s", exc)
        return {}


async def _summarize_messages(messages: list[dict]) -> str:
    """用於 ContextManager.maybe_compress 的摘要函數（注入給上下文管理器）。"""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        # 無 API Key 時降級：拼接前幾條
        snippets = [f"{m['role']}: {m['content'][:100]}" for m in messages[:5]]
        return "（歷史摘要）" + " | ".join(snippets)
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            system="請將以下對話歷史壓縮為簡潔摘要（200字以內），保留關鍵數據和結論。",
            messages=[{"role": "user", "content": str(messages)}],
            max_tokens=300,
        )
        return resp.content[0].text if resp.content else ""
    except Exception as exc:
        logger.warning("[runner] summarize_messages failed: %s", exc)
        return ""


async def run_agent(
    messages: list[dict],
    agent_name: str,
    context: dict | None = None,
    jwt_token: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> AsyncIterator[dict]:
    """
    多模型 tool_use 執行循環（async generator）。

    Layer 整合：
      Layer 1 (Brain):  多模型 ReAct 循環 + 用戶自定義指令注入
      Layer 2 (Memory): ContextManager 滑動窗口 + 摘要壓縮；結束後保存情景記憶
      Layer 3 (Tools):  execute_tool 工具調用（含 knowledge_search）

    model 參數優先級：
      1. 調用方顯式傳入
      2. 用戶個人配置 default_model_id（iam.user_agent_config）
      3. 環境變量 ANTHROPIC_MODEL
      4. 默認 claude-sonnet-4-6
    """
    # ── 加載用戶專屬 Agent 配置 ──────────────────────────────────
    user_cfg: dict = {}
    if user_id:
        user_cfg = await _load_user_agent_config(user_id)

    # model 優先級：調用方 > 用戶配置 > 環境變量 > 默認
    selected_model = model or user_cfg.get("default_model_id") or DEFAULT_MODEL
    provider = detect_provider(selected_model)

    # ── Layer 2: 上下文管理（短期記憶）────────────────────────────
    try:
        from aiagent.memory.context_manager import ContextManager
        cm = ContextManager(session_id=session_id)
        for m in messages:
            cm.add(m["role"], m["content"])
        await cm.maybe_compress(_summarize_messages)
        working_messages = cm.get_messages()
    except Exception:
        working_messages = messages   # 降級：直接使用原始消息

    system = load_agent_prompt(agent_name)

    # ── 注入用戶自定義指令（Layer 1 個人化） ─────────────────────
    custom_instr = user_cfg.get("custom_instructions", "")
    if custom_instr:
        system = f"【用戶個人指令】\n{custom_instr}\n\n{system}"

    if context:
        ctx_lines = []
        if context.get("fund_id"):    ctx_lines.append(f"當前基金：{context['fund_id']}")
        if context.get("as_of_date"): ctx_lines.append(f"估值日期：{context['as_of_date']}")
        if context.get("_plan"):      ctx_lines.append(context["_plan"])
        if ctx_lines:
            system = "【查詢上下文】\n" + "\n".join(ctx_lines) + "\n\n" + system

    # ── 加載用戶個人工具（動態擴展 tool_use） ────────────────────
    user_custom_tools: list[dict] = []
    if user_id and user_cfg.get("tools_enabled") != '["none"]':
        user_custom_tools = await _load_user_custom_tools(user_id)

    events: list[dict] = []
    tool_calls_used: list[dict] = []

    async def _collect(event: dict) -> None:
        events.append(event)
        if event.get("type") == "tool_call":
            tool_calls_used.append({"name": event.get("name"), "input": event.get("input")})

    # 根據 Provider 路由
    model_info = SUPPORTED_MODELS.get(selected_model, {})
    base_url   = model_info.get("base_url")

    # 合并系統工具 + 用戶個人工具（過濾掉內部字段 _user_tool/_endpoint/_method）
    all_tools = TOOLS + [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in user_custom_tools
    ]

    if provider == "openai":
        await _run_openai(working_messages, system, selected_model, _collect, extra_tools=all_tools)
    elif provider == "gemini":
        await _run_gemini(working_messages, system, selected_model, _collect)
    elif provider == "moonshot":
        await _run_openai(
            working_messages, system, selected_model, _collect,
            base_url=base_url or "https://api.moonshot.cn/v1",
            api_key_env="MOONSHOT_API_KEY",
            provider_label="Kimi（Moonshot）",
            extra_tools=all_tools,
        )
    elif provider == "deepseek":
        await _run_openai(
            working_messages, system, selected_model, _collect,
            base_url=base_url or "https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider_label="DeepSeek",
            extra_tools=all_tools,
        )
    elif provider == "openrouter":
        await _run_openai(
            working_messages, system, selected_model, _collect,
            base_url=base_url or _OPENROUTER_BASE,
            api_key_env="OPENROUTER_API_KEY",
            provider_label="OpenRouter",
            extra_tools=all_tools,
        )
    elif provider == "cursor":
        await _run_cursor(working_messages, system, selected_model, _collect, context=context)
    else:
        await _run_anthropic(working_messages, system, selected_model, _collect, extra_tools=all_tools)

    # ── Layer 2: 保存情景記憶（成功完成時）────────────────────────
    has_error = any(e.get("type") == "error" for e in events)
    if not has_error and events and session_id:
        text_parts = [e["content"] for e in events if e.get("type") == "text" and e.get("content")]
        summary = " ".join(text_parts)[:500]
        if summary and messages:
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            try:
                from aiagent.memory.vector_store import save_episode
                await save_episode(
                    agent_id=agent_name,
                    model_id=selected_model,
                    query=last_user[:500],
                    summary=summary,
                    tool_calls=tool_calls_used,
                    outcome="success",
                    user_id=user_id,
                )
            except Exception as exc:
                logger.debug("[runner] save_episode skipped: %s", exc)

    for event in events:
        yield event

    # 確保最後有 done
    if not events or events[-1].get("type") not in ("done", "error"):
        yield {"type": "done"}
