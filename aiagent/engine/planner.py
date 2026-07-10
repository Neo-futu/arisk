"""
aiagent/engine/planner.py — Layer 1: 控制與規劃層 — 任務拆解器

職責：
  判斷用戶請求是否需要多步規劃（Plan-and-Execute 模式），
  若需要則生成結構化執行計劃，並將計劃注入 system prompt 引導 Agent。

設計原則：
  - 輕量：不引入外部依賴，純 Python + LLM 調用
  - 可選：簡單問題直接 ReAct，複雜問題先 Plan 再 Execute
  - 透明：計劃作為 SSE 事件返回前端，用戶可見

複雜查詢判斷標準（滿足任一）：
  1. 涉及多個基金的對比分析
  2. 需要多個工具交叉驗證
  3. 包含「分析並生成報告」類綜合任務
  4. 問題中含有明確的多步驟指示詞
"""
from __future__ import annotations

import logging
import os
import re
from typing import TypedDict

logger = logging.getLogger(__name__)

# ── 觸發多步規劃的關鍵詞 ─────────────────────────────────────────
COMPLEX_PATTERNS = [
    r"(對比|比較|對照).*(基金|portfolio)",
    r"(分析|計算).*(並|同時|然後|接著).*(生成|輸出|報告)",
    r"全面|完整|詳細.*(分析|報告|評估)",
    r"(第一|首先|然後|最後|步驟|step)",
    r"(WAM|WAL|VaR|持倉|合規).*(WAM|WAL|VaR|持倉|合規)",  # 多指標組合
]

# ── 計劃類型 ─────────────────────────────────────────────────────
class PlanStep(TypedDict):
    step:        int
    description: str
    tools:       list[str]   # 預期使用的工具

class Plan(TypedDict):
    title:  str
    steps:  list[PlanStep]
    reason: str              # 為什麼需要多步驟


def needs_planning(user_message: str) -> bool:
    """
    判斷是否需要多步規劃。
    快速啟發式判斷，不調用 LLM。
    """
    text = user_message.lower()
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, user_message, re.IGNORECASE):
            return True
    # 超過 100 字且含多個問號 → 複合問題
    if len(user_message) > 100 and user_message.count("？") + user_message.count("?") >= 2:
        return True
    return False


async def create_plan(
    user_message: str,
    agent_name:   str,
    model:        str | None = None,
) -> Plan | None:
    """
    調用 LLM 生成結構化執行計劃。

    Returns:
        Plan TypedDict，或 None（LLM 不可用時降級）
    """
    if not needs_planning(user_message):
        return None

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return _heuristic_plan(user_message)

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model or "claude-haiku-4-5-20251001",
            system=_PLAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=600,
        )
        text = resp.content[0].text if resp.content else ""
        return _parse_plan(text) or _heuristic_plan(user_message)
    except Exception as exc:
        logger.warning("[Planner] LLM plan failed: %s, using heuristic", exc)
        return _heuristic_plan(user_message)


def plan_to_system_injection(plan: Plan) -> str:
    """將計劃轉化為 system prompt 注入文本，引導 Agent 按步驟執行。"""
    lines = [
        f"【執行計劃 — {plan['title']}】",
        f"原因：{plan['reason']}",
        "請按以下步驟逐步完成任務：",
    ]
    for s in plan["steps"]:
        tools_str = "、".join(s["tools"]) if s["tools"] else "思考推理"
        lines.append(f"  步驟 {s['step']}：{s['description']}（工具：{tools_str}）")
    lines.append("\n完成每個步驟後報告進度，全部完成後輸出綜合結論。")
    return "\n".join(lines)


# ── 私有：LLM 輸出解析 ────────────────────────────────────────────

_PLAN_SYSTEM_PROMPT = """你是 ARISK 風控平台的任務規劃助手。
根據用戶的複雜分析請求，生成簡潔的執行計劃。

輸出格式（嚴格遵守）：
TITLE: <計劃標題>
REASON: <為什麼需要多步驟>
STEP 1: <步驟描述> | TOOLS: <tool1,tool2>
STEP 2: <步驟描述> | TOOLS: <tool1>
STEP 3: <步驟描述> | TOOLS: <none>

可用工具：get_system_info, get_exposure, get_var, get_var_compare, get_positions, get_nav_history, sector_overview, knowledge_search
最多 5 個步驟，每個步驟一行。"""


def _parse_plan(text: str) -> Plan | None:
    try:
        title  = re.search(r"TITLE:\s*(.+)", text)
        reason = re.search(r"REASON:\s*(.+)", text)
        steps_raw = re.findall(r"STEP\s*(\d+):\s*(.+?)\s*\|\s*TOOLS:\s*(.+)", text)
        if not title or not steps_raw:
            return None
        steps: list[PlanStep] = []
        for num, desc, tools_str in steps_raw:
            tools = [t.strip() for t in tools_str.split(",") if t.strip() and t.strip() != "none"]
            steps.append({"step": int(num), "description": desc.strip(), "tools": tools})
        return Plan(
            title=title.group(1).strip(),
            reason=(reason.group(1).strip() if reason else "複雜多步驟任務"),
            steps=steps,
        )
    except Exception:
        return None


def _heuristic_plan(user_message: str) -> Plan:
    """啟發式計劃（LLM 不可用時的降級）。"""
    return Plan(
        title="多步分析任務",
        reason="任務包含多個分析維度，需要分步完成",
        steps=[
            PlanStep(step=1, description="獲取系統基礎信息（基金列表、當前日期）", tools=["get_system_info"]),
            PlanStep(step=2, description="執行數據查詢和風險計算",                tools=["get_exposure", "get_var_compare"]),
            PlanStep(step=3, description="整合分析結果，輸出結論報告",             tools=[]),
        ],
    )
