"""Turn RiskEngine / Business results into an Agent explanation. No calculations."""
from __future__ import annotations

from typing import Any


def explain(agent: str, intent: str, result: dict[str, Any]) -> str:
    if not result.get("ok", True) and result.get("error"):
        err = result["error"]
        return f"{agent} 未能完成 {intent}：{err.get('code')} {err.get('message')}"

    payload = result.get("payload") if isinstance(result.get("payload"), dict) else result
    kpi = payload.get("kpi") or payload.get("analytic")
    engine = payload.get("engine") or (payload.get("context") or {}).get("engine")
    if kpi:
        value = payload.get("result") or payload.get("base_pv") or payload.get("pnl")
        engine_note = f"，引擎 {engine}" if engine else ""
        return f"{agent} 已通过 Business API / RiskEngine 取得 {kpi}{engine_note}。Agent 未自行计算。"
    if payload.get("sim_id"):
        return (
            f"{agent} 已在 Simulation Portfolio {payload['sim_id']} 上完成 {intent}。"
            "Live Portfolio 未被直接修改。"
        )
    if payload.get("layer") == "Tool Connectivity Layer":
        return f"{agent} 经 MCP 连接层取得 {payload.get('capability')} 连通性，计算仍由 RiskEngine 负责。"
    return f"{agent} 已完成 {intent}。结果来自 Business API / RiskEngine，Agent 只做说明。"
