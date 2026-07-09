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

import json
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv

from .tools import TOOLS, execute_tool

load_dotenv()
logger = logging.getLogger(__name__)

# ── 路徑 ──────────────────────────────────────────────────────────
AGENTS_DIR    = Path(__file__).parent.parent / "agents"
MAX_TOOL_LOOPS = 10

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
    # xAI Grok via OpenRouter — 需設置 OPENROUTER_API_KEY，香港無地區限制
    "x-ai/grok-4.20":              {"provider": "openrouter", "label": "xAI Grok 4.20（最新旗艦，香港可用）",
                                    "base_url": "https://openrouter.ai/api/v1"},
    "x-ai/grok-4.3":               {"provider": "openrouter", "label": "xAI Grok 4.3（香港可用）",
                                    "base_url": "https://openrouter.ai/api/v1"},
}

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def detect_provider(model: str) -> str:
    """根據模型名稱前綴自動識別 Provider。"""
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
    # 也從 SUPPORTED_MODELS 查詢（優先）
    info = SUPPORTED_MODELS.get(model, {})
    if info.get("provider"):
        return info["provider"]
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

    while loop_count < MAX_TOOL_LOOPS:
        loop_count += 1
        try:
            response = client.messages.create(
                model=model,
                system=system,
                messages=working_messages,
                tools=TOOLS,
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


# ── OpenAI 執行 ───────────────────────────────────────────────────
async def _run_openai(
    messages: list[dict],
    system: str,
    model: str,
    stream_callback,
    base_url: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
    provider_label: str = "OpenAI",
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
    oai_tools = _tools_for_openai(TOOLS)
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


async def run_agent(
    messages: list[dict],
    agent_name: str,
    context: dict | None = None,
    jwt_token: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict]:
    """
    多模型 tool_use 執行循環（async generator）。

    model 參數優先級：
      1. 調用方顯式傳入
      2. 環境變量 ANTHROPIC_MODEL
      3. 默認 claude-sonnet-4-6
    """
    selected_model = model or DEFAULT_MODEL
    provider = detect_provider(selected_model)

    system = load_agent_prompt(agent_name)
    if context:
        ctx_lines = []
        if context.get("fund_id"):    ctx_lines.append(f"當前基金：{context['fund_id']}")
        if context.get("as_of_date"): ctx_lines.append(f"估值日期：{context['as_of_date']}")
        if ctx_lines:
            system = "【查詢上下文】\n" + "\n".join(ctx_lines) + "\n\n" + system

    events: list[dict] = []

    async def _collect(event: dict) -> None:
        events.append(event)

    # 根據 Provider 路由
    model_info = SUPPORTED_MODELS.get(selected_model, {})
    base_url   = model_info.get("base_url")

    if provider == "openai":
        await _run_openai(messages, system, selected_model, _collect)
    elif provider == "gemini":
        await _run_gemini(messages, system, selected_model, _collect)
    elif provider == "moonshot":
        await _run_openai(
            messages, system, selected_model, _collect,
            base_url=base_url or "https://api.moonshot.cn/v1",
            api_key_env="MOONSHOT_API_KEY",
            provider_label="Kimi（Moonshot）",
        )
    elif provider == "deepseek":
        await _run_openai(
            messages, system, selected_model, _collect,
            base_url=base_url or "https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider_label="DeepSeek",
        )
    elif provider == "openrouter":
        await _run_openai(
            messages, system, selected_model, _collect,
            base_url=base_url or "https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            provider_label="OpenRouter xAI Grok",
        )
    else:
        await _run_anthropic(messages, system, selected_model, _collect)

    for event in events:
        yield event

    # 確保最後有 done
    if not events or events[-1].get("type") not in ("done", "error"):
        yield {"type": "done"}
