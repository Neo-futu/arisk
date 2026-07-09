"""
aiagent/scripts/orchestrate.py — 多 Agent 協調事件循環

整合自 claude-risk-agent/scripts/orchestrate.py。
處理跨 Agent handoff（從一個 Agent 委派到另一個 Agent）的參考實現。

在 ARISK 中，handoff 模式用於：
  risk-analyst → market-researcher（市場背景研究）
  risk-analyst → compliance-officer（合規深度核查）
  compliance-officer → report-writer（生成合規報告）

Handoff 觸發方式：Agent 回覆中包含 handoff_request JSON 塊：
  {"handoff_request": {"target_agent": "compliance-officer", "payload": {...}}}

安全機制（同 claude-risk-agent）：
  - ALLOWED_TARGETS 白名單
  - jsonschema payload 校驗
  - 防止文檔內嵌入注入

用法（參考，實際由 6_entry/agent_v2.py 調用）：
  python aiagent/scripts/orchestrate.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── 允許的 handoff 目標（白名單） ─────────────────────────────────
ALLOWED_TARGETS: set[str] = {
    "risk-analyst",
    "compliance-officer",
    "fund-reporter",
    "market-researcher",
    "gl-reconciler",
    "kyc-screener",
    "statement-auditor",
    "valuation-reviewer",
    "month-end-closer",
}

HANDOFF_SCHEMA = {
    "type": "object",
    "properties": {
        "target_agent": {"type": "string"},
        "payload":      {"type": "object"},
        "context":      {"type": "object"},
    },
    "required": ["target_agent", "payload"],
}


def extract_handoff(text: str) -> dict | None:
    """從 Agent 輸出文字中提取 handoff_request JSON 塊。"""
    # 匹配 {"handoff_request": {...}} 格式
    m = re.search(r'\{"handoff_request"\s*:\s*(\{[^}]+(?:\{[^}]*\}[^}]*)?\})', text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def validate_handoff(payload: dict) -> tuple[bool, str]:
    """校驗 handoff payload 的安全性和格式。"""
    try:
        import jsonschema
        jsonschema.validate(instance=payload, schema=HANDOFF_SCHEMA)
    except ImportError:
        pass  # 沒有 jsonschema 時跳過
    except Exception as e:
        return False, f"Schema 校驗失敗：{e}"

    target = payload.get("target_agent", "")
    if target not in ALLOWED_TARGETS:
        return False, f"目標 Agent '{target}' 不在白名單中"

    return True, "ok"


def route_handoff(handoff: dict, runner_fn=None) -> dict:
    """
    路由 handoff 到目標 Agent。

    runner_fn: 可選的 Agent 執行函數，簽名為 (agent_name, messages, context) -> str
    默認返回 handoff 元數據供外層處理。
    """
    valid, msg = validate_handoff(handoff)
    if not valid:
        return {"error": msg, "handoff": handoff}

    target  = handoff["target_agent"]
    payload = handoff.get("payload", {})
    context = handoff.get("context", {})

    if runner_fn:
        result = runner_fn(target, [{"role": "user", "content": str(payload)}], context)
        return {"target": target, "result": result}

    return {
        "target":  target,
        "payload": payload,
        "context": context,
        "status":  "pending",   # 由調用方實際執行
    }


if __name__ == "__main__":
    # 演示用法
    sample_output = '''
    分析完成。需要進行合規深度核查：
    {"handoff_request": {"target_agent": "compliance-officer", "payload": {"fund_id": "BHMMF001", "as_of_date": "2026-06-25"}, "context": {"reason": "WAM 接近限額，需要逐條守則核查"}}}
    '''
    handoff = extract_handoff(sample_output)
    if handoff:
        print("提取到 handoff_request:", json.dumps(handoff, ensure_ascii=False, indent=2))
        result = route_handoff(handoff)
        print("路由結果:", json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("未找到 handoff_request")
