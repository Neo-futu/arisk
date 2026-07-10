"""
aiagent/orchestrator/supervisor.py — Layer 4: 多 Agent 路由督導

職責：
  根據用戶意圖，將請求路由到最合適的專業 Agent。
  支持兩種路由策略：
    1. 啟發式路由（快速，無 LLM 調用）— 關鍵詞匹配
    2. LLM 路由（精準，多一次 API 調用）— 讓 Claude 判斷

路由規則：
  user_message → agent_id 映射，基於金融業務語義

多 Agent 協作模式（Handoff）：
  supervisor 可以觸發多個 Agent 串行執行：
    request → supervisor → [risk-analyst → compliance-officer] → 合并輸出
  handoff 通過 yield {"type": "handoff", "to": agent_id} 事件通知 stream.py
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── 路由規則（啟發式，從精確到寬泛） ─────────────────────────────
_ROUTING_RULES: list[tuple[str, str, str]] = [
    # (正則模式, agent_id, 描述)
    (r"KYC|盡職調查|身份核實|洗錢|AML",              "kyc-screener",       "KYC/AML 合規篩查"),
    (r"GL|總賬|對賬|配對|reconcil",                  "gl-reconciler",      "GL 對賬"),
    (r"月末|結賬|month.?end|close",                  "month-end-closer",   "月末結賬"),
    (r"NAV|淨值|報表.*審計|審計.*報表",               "statement-auditor",  "NAV 報表審計"),
    (r"估值|valuation|定價|pricing",                 "valuation-reviewer", "組合估值審查"),
    (r"合規|SFC|守則|regulatory|規例|compliance",    "compliance-officer", "SFC 合規審查"),
    (r"報告|月報|日報|factsheet|report|分析報告",     "fund-reporter",      "基金報表生成"),
    (r"市場|行業|HIBOR|利率|sector|market|信用",      "market-researcher",  "市場研究"),
    (r"VaR|風險|暴露|WAM|WAL|持倉|exposure|position", "risk-analyst",       "風控分析"),
]

# ── 需要多 Agent 協作的複合任務 ──────────────────────────────────
_MULTI_AGENT_TRIGGERS: list[tuple[str, list[str]]] = [
    (r"(合規|SFC).*(VaR|風險|WAM)", ["risk-analyst", "compliance-officer"]),
    (r"(風險|VaR).*(合規|守則)",    ["risk-analyst", "compliance-officer"]),
    (r"完整報告|全面分析|綜合評估",  ["risk-analyst", "compliance-officer", "fund-reporter"]),
]


def route_to_agent(
    user_message: str,
    current_agent: str = "general",
) -> str:
    """
    啟發式路由：根據消息內容推薦最合適的 Agent ID。

    Args:
        user_message:  用戶原始消息
        current_agent: 當前選中的 Agent（如已選擇合適 Agent 則不覆蓋）

    Returns:
        推薦的 agent_id
    """
    if current_agent != "general":
        return current_agent  # 用戶已明確選擇，不覆蓋

    for pattern, agent_id, _ in _ROUTING_RULES:
        if re.search(pattern, user_message, re.IGNORECASE):
            logger.info("[Supervisor] route '%s...' → %s", user_message[:30], agent_id)
            return agent_id

    return "general"


def needs_multi_agent(user_message: str) -> list[str] | None:
    """
    判斷是否需要多 Agent 協作。
    返回 Agent ID 列表（按執行順序），或 None（單 Agent 即可）。
    """
    for pattern, agents in _MULTI_AGENT_TRIGGERS:
        if re.search(pattern, user_message, re.IGNORECASE):
            logger.info("[Supervisor] multi-agent triggered: %s", agents)
            return agents
    return None


class Supervisor:
    """
    Supervisor 督導器：管理多 Agent 協作流程。

    用法（在 sse_generator 外層調用）：
        supervisor = Supervisor()
        async for event in supervisor.run(messages, context):
            yield event
    """

    def __init__(self) -> None:
        self._handoff_count = 0
        self._max_handoffs  = 3    # 防止無限 handoff 循環

    async def run(
        self,
        messages:    list[dict],
        agent_name:  str,
        context:     dict | None,
        jwt_token:   str | None,
        model:       str | None,
        session_id:  str | None = None,
        user_id:     str | None = None,
    ):
        """
        執行 Agent 任務，支持 multi-agent handoff。
        若請求需要多 Agent，按順序執行並合并輸出。
        """
        from aiagent.engine.stream import sse_generator

        user_query = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        # 判斷是否需要多 Agent
        agent_chain = needs_multi_agent(user_query)

        if agent_chain and len(agent_chain) > 1:
            yield _sse({"type": "supervisor", "message": f"複合任務，將依次調用：{' → '.join(agent_chain)}"})

            combined_output: list[str] = []
            for i, agent_id in enumerate(agent_chain):
                if self._handoff_count >= self._max_handoffs:
                    break
                self._handoff_count += 1

                if i > 0:
                    yield _sse({"type": "handoff", "from": agent_chain[i-1], "to": agent_id})
                    # 把前一個 Agent 的輸出加入下一個 Agent 的上下文
                    if combined_output:
                        handoff_msg = f"【上一步分析結果】\n{''.join(combined_output[-1:])}"
                        messages = messages + [{"role": "assistant", "content": handoff_msg}]

                step_output: list[str] = []
                async for event in sse_generator(
                    messages=messages,
                    agent_name=agent_id,
                    context=context,
                    jwt_token=jwt_token,
                    model=model,
                    session_id=session_id,
                    user_id=user_id,
                ):
                    # 透傳所有事件
                    if '"type": "done"' not in event and '"type": "start"' not in event:
                        yield event
                    if '"type": "text"' in event:
                        import json as _json
                        try:
                            ev = _json.loads(event.removeprefix("data: ").strip())
                            step_output.append(ev.get("content", ""))
                        except Exception:
                            pass

                combined_output.append("".join(step_output))
        else:
            # 單 Agent 執行（透傳給 sse_generator）
            async for event in sse_generator(
                messages=messages,
                agent_name=agent_name,
                context=context,
                jwt_token=jwt_token,
                model=model,
                session_id=session_id,
                user_id=user_id,
            ):
                yield event


def _sse(event: dict) -> str:
    import json
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
