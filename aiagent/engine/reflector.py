"""
aiagent/engine/reflector.py — Layer 1: 控制與規劃層 — 自我反思模塊

職責：
  Agent 完成一輪工具調用後，對輸出進行質量評估：
    1. detect_issues()    — 識別常見問題（空數據、幻覺、邏輯錯誤）
    2. should_retry()     — 判斷是否需要重試或追加查詢
    3. get_correction()   — 生成修正建議，注入下一輪上下文

觸發場景：
  - 工具返回 sample_size=0 或 data=null
  - 輸出中含有「我無法」「無法確認」等不確定語句
  - 數字結論與工具返回數據不一致（啟發式檢測）

設計原則：
  - 非阻塞：反思在主循環結束後執行，不影響 SSE 流
  - 輕量：優先啟發式規則，LLM 反思為可選增強
  - 最大重試：MAX_REFLECT_ROUNDS = 2（避免無限循環）
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_REFLECT_ROUNDS = 2    # 最多反思重試次數

# ── 問題模式 ─────────────────────────────────────────────────────
_EMPTY_DATA_PATTERNS = [
    r"sample_size.*?[:\s]+0",
    r'"count":\s*0',
    r'"positions":\s*\[\s*\]',
    r"no data|no result|not found|未找到|無數據|暫無",
]

_UNCERTAINTY_PATTERNS = [
    r"我無法|無法確認|無法獲取|抱歉|我不知道",
    r"I cannot|I don't know|unable to|sorry",
    r"可能是|大概|估計|猜測",    # 推測性語言（應基於工具數據）
]

_HALLUCINATION_RISK = [
    r"\d+\.\d+%",   # 具體百分比（需確認來自工具）
    r"HKD\s*[\d,]+",
    r"億|百萬",
]


class ReflectionResult:
    """反思結果。"""

    def __init__(
        self,
        has_issue:   bool,
        issue_type:  str | None,
        description: str,
        suggestion:  str,
        should_retry: bool,
    ) -> None:
        self.has_issue   = has_issue
        self.issue_type  = issue_type
        self.description = description
        self.suggestion  = suggestion
        self.should_retry = should_retry

    def to_system_injection(self) -> str:
        if not self.has_issue:
            return ""
        return (
            f"【反思提示】前一輪輸出存在問題：{self.description}\n"
            f"建議：{self.suggestion}\n"
            "請重新調用相關工具獲取準確數據後再回答。"
        )


def detect_issues(
    agent_output: str,
    tool_results: list[dict[str, Any]],
) -> ReflectionResult:
    """
    啟發式問題檢測（不調用 LLM，即時執行）。

    Args:
        agent_output:  Agent 的最終文字輸出
        tool_results:  工具調用結果列表 [{name, result}]
    """
    # 1. 工具返回空數據
    for tr in tool_results:
        result_str = str(tr.get("result", ""))
        for pattern in _EMPTY_DATA_PATTERNS:
            if re.search(pattern, result_str, re.IGNORECASE):
                return ReflectionResult(
                    has_issue=True,
                    issue_type="empty_data",
                    description=f"工具 '{tr.get('name')}' 返回空數據",
                    suggestion="請確認基金 ID 和日期是否正確，可調用 get_system_info 重新確認",
                    should_retry=True,
                )

    # 2. Agent 輸出含不確定性語言
    for pattern in _UNCERTAINTY_PATTERNS:
        if re.search(pattern, agent_output, re.IGNORECASE):
            return ReflectionResult(
                has_issue=True,
                issue_type="uncertainty",
                description="輸出包含不確定性語言，可能未充分利用工具數據",
                suggestion="請重新調用相關工具獲取確定性數據",
                should_retry=len(tool_results) == 0,  # 未使用工具時才重試
            )

    # 3. 輸出含具體數字但未調用任何工具（幻覺風險）
    if not tool_results:
        for pattern in _HALLUCINATION_RISK:
            if re.search(pattern, agent_output):
                return ReflectionResult(
                    has_issue=True,
                    issue_type="potential_hallucination",
                    description="輸出含具體數字但未調用工具驗證",
                    suggestion="所有數字結論必須來自工具返回數據，請先調用相關工具",
                    should_retry=True,
                )

    return ReflectionResult(
        has_issue=False,
        issue_type=None,
        description="輸出質量正常",
        suggestion="",
        should_retry=False,
    )


def should_retry(
    reflection: ReflectionResult,
    current_round: int,
) -> bool:
    """
    綜合判斷是否需要重試。

    Args:
        reflection:    detect_issues() 的結果
        current_round: 當前已執行的反思輪次（從 0 開始）
    """
    if current_round >= MAX_REFLECT_ROUNDS:
        return False
    return reflection.has_issue and reflection.should_retry


# ── 可選：LLM 深度反思 ────────────────────────────────────────────

async def llm_reflect(
    user_query:   str,
    agent_output: str,
    tool_results: list[dict],
) -> str | None:
    """
    調用 LLM 對輸出進行深度評估（可選，用於複雜任務）。
    返回改進建議字符串，或 None（LLM 不可用）。
    """
    import os
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=key)
        prompt = (
            f"用戶問題：{user_query[:200]}\n\n"
            f"Agent 回答：{agent_output[:500]}\n\n"
            f"工具調用：{[t.get('name') for t in tool_results]}\n\n"
            "請評估以上回答是否準確完整（50字以內），如有問題請給出具體改進方向："
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            system="你是 AI Agent 輸出的質量評估員，專注於金融數據準確性。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        return resp.content[0].text if resp.content else None
    except Exception as exc:
        logger.debug("[Reflector] LLM reflect failed: %s", exc)
        return None
