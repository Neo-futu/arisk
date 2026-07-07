"""
Orchestrator — ARISK Agent 事件循環。

職責：
1. 接收 agent 的 handoff_request 事件
2. 在交接前插入人工審核檢查點（human-in-the-loop）
3. 路由到正確的子 agent
4. 監控 agent 執行狀態和審核狀態

設計參考：
- managed-agent-cookbooks/ 的 orchestrate.py 模式
- human-review SKILL.md 的審核觸發矩陣

數據流：
  orchestrator
      ↓ callable data-puller（只讀）
      ↓ callable risk-calculator（只讀計算）
    ↓ [人工審核點 ①] — 如有 breach_flags
    ↓ [人工審核點 ①.5] — 如 VaR 超閾值（預設 > 5% NAV）
      ↓ callable report-writer（write-holder）
      ↓ [人工審核點 ②] — 報告發布前
      ↓ 完成，返回 artefact 路徑
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import httpx

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

try:
    from .report_writer_runtime import generate_risk_report
except ImportError:
    from report_writer_runtime import generate_risk_report

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PROCESSING_API_URL = os.environ.get("PROCESSING_API_URL", "http://localhost:8001")
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

_api_headers = {"X-API-Key": PROCESSING_API_KEY}


# ─── 事件類型 ────────────────────────────────────────────────────

HANDOFF_REQUEST = "handoff_request"       # agent 請求交接到下一個子 agent
REVIEW_REQUIRED = "review_required"       # agent 要求人工審核
TASK_COMPLETE   = "task_complete"         # 任務完成
TASK_FAILED     = "task_failed"           # 任務失敗


class OrchestratorEvent:
    def __init__(self, event_type: str, payload: dict):
        self.event_type = event_type
        self.payload = payload
        self.event_id = str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat()


# ─── 主 Orchestrator ─────────────────────────────────────────────

class RiskAgentOrchestrator:
    """
    Risk Agent 的 orchestrator。管理多個子 agent 的執行順序，
    在關鍵交接點插入人工審核。
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if anthropic else None
        self.http = httpx.AsyncClient(
            base_url=PROCESSING_API_URL,
            headers=_api_headers,
            timeout=120,
        )
        self.task_log: list[dict] = []

    async def run(
        self,
        fund_id: str,
        as_of_date: str,
        task_id: str | None = None,
        skip_review: bool = False,
        risk_only: bool = False,
    ) -> dict:
        """
        完整執行 risk-agent 工作流：
        data-puller → risk-calculator → [審核①] → [審核①.5] → report-writer → [審核②]

        skip_review=True 僅用於測試環境。
        risk_only=True 僅跑到 risk-calculator，便於日常巡檢。
        """
        task_id = task_id or str(uuid.uuid4())
        self._log(
            task_id,
            "ORCHESTRATOR_START",
            {"fund_id": fund_id, "as_of_date": as_of_date, "risk_only": risk_only},
        )

        try:
            # ── Step 1: Data Puller（只讀） ──────────────────────
            self._log(task_id, "INVOKE_SUBAGENT", {"agent": "data-puller"})
            positions_data = await self._invoke_data_puller(fund_id, as_of_date)

            # ── Step 2: Risk Calculator（只讀計算） ───────────────
            self._log(task_id, "INVOKE_SUBAGENT", {"agent": "risk-calculator"})
            risk_package = await self._invoke_risk_calculator(task_id, fund_id, as_of_date)
            exposure_result = risk_package["exposure"]
            var_results = risk_package["var_results"]
            max_var_pct_nav = risk_package["max_var_pct_nav"]

            risk_result = {
                "fund_id": fund_id,
                "as_of_date": as_of_date,
                "exposure": exposure_result,
                "var_results": var_results,
                "max_var_pct_nav": max_var_pct_nav,
                "primary_var": var_results[0] if var_results else {},
                "is_compliant": exposure_result.get("is_compliant", True),
                "breach_flags": exposure_result.get("breach_flags", {}),
                "wam_days": exposure_result.get("wam_days"),
                "wal_days": exposure_result.get("wal_days"),
                "daily_liquid_pct": exposure_result.get("daily_liquid_pct"),
                "weekly_liquid_pct": exposure_result.get("weekly_liquid_pct"),
            }

            if risk_only:
                self._log(task_id, "RISK_ONLY_COMPLETE", {"max_var_pct_nav": max_var_pct_nav})
                return {
                    "task_id": task_id,
                    "status": "risk_only_completed",
                    "risk_summary": risk_result,
                    "task_log": self.task_log,
                }

            # ── 審核點 ①：合規違規檢查 ───────────────────────────
            breach_flags = risk_result.get("breach_flags", {})
            if breach_flags and not skip_review:
                self._log(task_id, "REVIEW_GATE_①", {"breach_flags": breach_flags})
                review_decision = await self._human_review_gate(
                    task_id=task_id,
                    category="COMPLIANCE_BREACH",
                    title=f"合規違規：{', '.join(breach_flags.keys())}",
                    summary=self._format_breach_summary(fund_id, as_of_date, risk_result),
                    fund_id=fund_id,
                    as_of_date=as_of_date,
                    payload={"risk_result": risk_result},
                )
                if review_decision == "REJECTED":
                    return self._abort(task_id, "合規違規審核被拒絕，已中止報告生成")

            # ── 審核點 ①.5：高風險 VaR 檢查 ──────────────────────
            if max_var_pct_nav > 5 and not skip_review:
                self._log(task_id, "REVIEW_GATE_HIGH_RISK", {"max_var_pct_nav": max_var_pct_nav})
                review_decision = await self._human_review_gate(
                    task_id=task_id,
                    category="HIGH_RISK",
                    title=f"高風險告警：VaR={max_var_pct_nav:.2f}% NAV",
                    summary=(
                        f"基金 {fund_id} 在 {as_of_date} 的 VaR 超過 5% NAV 閾值。"
                        f"最高 VaR 佔比：{max_var_pct_nav:.2f}%（三方法口徑）。"
                    ),
                    fund_id=fund_id,
                    as_of_date=as_of_date,
                    payload={"var_results": var_results, "max_var_pct_nav": max_var_pct_nav},
                )
                if review_decision == "REJECTED":
                    return self._abort(task_id, "高風險 VaR 審核被拒絕，已中止報告生成")

            # ── Step 3: Report Writer（write-holder） ─────────────
            self._log(task_id, "INVOKE_SUBAGENT", {"agent": "report-writer"})
            report_result = await self._invoke_report_writer(
                fund_id, as_of_date, risk_result, positions_data
            )
            artefact_path = report_result.get("artefact_path")
            artefact_url  = report_result.get("artefact_url")

            # ── 審核點 ②：報告發布前 ──────────────────────────────
            if not skip_review:
                self._log(task_id, "REVIEW_GATE_②", {"artefact_path": artefact_path})
                review_decision = await self._human_review_gate(
                    task_id=task_id,
                    category="REPORT_PUBLISH",
                    title=f"報告發布審核：{fund_id} {as_of_date}",
                    summary=f"報告已生成，待批准後對外發布。文件：{artefact_path}",
                    fund_id=fund_id,
                    as_of_date=as_of_date,
                    payload={"report_summary": report_result.get("summary", "")},
                    artefact_path=artefact_path,
                    artefact_url=artefact_url,
                )
                if review_decision == "REJECTED":
                    return self._abort(task_id, "報告發布被拒絕，報告保留在 artefacts/ 但未發布")

            self._log(task_id, "TASK_COMPLETE", {"artefact_url": artefact_url})
            return {
                "task_id": task_id,
                "status": "completed",
                "artefact_path": artefact_path,
                "artefact_url": artefact_url,
                "risk_summary": risk_result,
                "task_log": self.task_log,
            }

        except Exception as e:
            self._log(task_id, "TASK_FAILED", {"error": str(e)})
            logger.exception("Orchestrator failed for task %s", task_id)
            raise
        finally:
            await self.http.aclose()

    # ─── 子 Agent 調用 ───────────────────────────────────────────

    async def _invoke_data_puller(self, fund_id: str, as_of_date: str) -> dict:
        """調用 data-puller：只讀取數據，不計算。"""
        resp = await self.http.get(
            f"/positions/{fund_id}/summary",
            params={"as_of_date": as_of_date},
        )
        resp.raise_for_status()
        return resp.json()

    async def _invoke_risk_calculator(self, task_id: str, fund_id: str, as_of_date: str) -> dict:
        """調用 risk-calculator：計算暴露與三方法 VaR，返回聚合結果（不寫 DB）。"""
        exposure_resp = await self.http.get(
            f"/risk/exposure/{fund_id}",
            params={"as_of_date": as_of_date},
        )
        exposure_resp.raise_for_status()

        var_methods = ("historical", "monte_carlo", "distribution")
        var_results = await asyncio.gather(
            *[self._fetch_var_method(task_id, fund_id, as_of_date, method) for method in var_methods]
        )
        max_var_pct_nav = max((float(v.get("var_pct_nav", 0.0) or 0.0) for v in var_results), default=0.0)

        return {
            "exposure": exposure_resp.json(),
            "var_results": var_results,
            "max_var_pct_nav": max_var_pct_nav,
        }

    async def _fetch_var_method(self, task_id: str, fund_id: str, as_of_date: str, method: str) -> dict:
        """Fetch one VaR method with graceful fallback on upstream errors."""
        try:
            resp = await self.http.get(
                f"/risk/var/{fund_id}",
                params={"as_of_date": as_of_date, "method": method, "confidence": 0.99, "horizon_days": 1},
            )
            resp.raise_for_status()
            payload = resp.json()
            payload["method_requested"] = method
            return payload
        except Exception as exc:
            self._log(
                task_id,
                "VAR_FETCH_FAILED",
                {"fund_id": fund_id, "as_of_date": as_of_date, "method": method, "error": str(exc)},
            )
            return {
                "fund_id": fund_id,
                "as_of_date": as_of_date,
                "confidence": 0.99,
                "horizon_days": 1,
                "var_hkd": 0.0,
                "var_pct_nav": 0.0,
                "cvar_hkd": 0.0,
                "method": "INSUFFICIENT_DATA",
                "method_requested": method,
                "sample_size": 0,
            }

    async def _invoke_report_writer(
        self,
        fund_id: str,
        as_of_date: str,
        risk_result: dict,
        positions_data: dict,
    ) -> dict:
        """
        調用 report-writer（write-holder）：生成 xlsx 報告。
        這是唯一向 artefacts/ 寫入的步驟。
        """
        return await asyncio.to_thread(
            generate_risk_report,
            fund_id,
            as_of_date,
            risk_result,
            positions_data,
        )

    # ─── 人工審核交接 ─────────────────────────────────────────────

    async def _human_review_gate(
        self,
        task_id: str,
        category: str,
        title: str,
        summary: str,
        fund_id: str,
        as_of_date: str,
        payload: dict,
        artefact_path: str | None = None,
        artefact_url: str | None = None,
    ) -> str:
        """
        向 Processing API 提交審核請求並等待決策。

        這是 human-in-the-loop 的核心實現點。
        返回 "APPROVED" | "REJECTED" | "TIMEOUT"
        """
        # 提交審核請求
        review_resp = await self.http.post(
            "/review/request",
            json={
                "category": category,
                "title": title,
                "summary": summary,
                "triggered_by": f"orchestrator:{task_id}",
                "fund_id": fund_id,
                "as_of_date": as_of_date,
                "task_id": task_id,
                "payload": payload,
                "artefact_path": artefact_path,
                "artefact_url": artefact_url,
            },
        )
        review_resp.raise_for_status()
        review_id = review_resp.json()["review_id"]

        self._log(task_id, "REVIEW_SUBMITTED", {"review_id": review_id, "category": category})
        logger.info("Waiting for human review: %s (category=%s)", review_id, category)

        # 輪詢等待決策（生產環境改用 Redis pub/sub）
        max_wait = 3600
        poll_interval = 5
        elapsed = 0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await self.http.get(f"/review/{review_id}")
            if status_resp.status_code != 200:
                break
            data = status_resp.json()
            status = data.get("status")

            if status == "APPROVED":
                self._log(task_id, "REVIEW_APPROVED", {"review_id": review_id})
                return "APPROVED"
            elif status in ("REJECTED", "EXPIRED"):
                self._log(task_id, "REVIEW_REJECTED", {"review_id": review_id, "status": status})
                return "REJECTED"

        logger.warning("Review timed out: %s", review_id)
        self._log(task_id, "REVIEW_TIMEOUT", {"review_id": review_id})
        return "TIMEOUT"

    # ─── 輔助方法 ─────────────────────────────────────────────────

    def _format_breach_summary(self, fund_id: str, as_of_date: str, risk_result: dict) -> str:
        breach_flags = risk_result.get("breach_flags", {})
        lines = [
            f"基金 {fund_id} 在 {as_of_date} 發現以下 SFC 守則違規：",
            "",
        ]
        flag_map = {
            "WAM_BREACH": f"WAM = {risk_result.get('wam_days', 'N/A'):.1f} 天，超過 60 天上限（第8.2(f)條）",
            "WAL_BREACH": f"WAL = {risk_result.get('wal_days', 'N/A'):.1f} 天，超過 120 天上限（第8.2(f)條）",
            "DAILY_LIQUID_BREACH": f"每日流動資產 = {risk_result.get('daily_liquid_pct', 'N/A'):.2f}%，低於 7.5% 下限（第8.2(n)條）",
            "WEEKLY_LIQUID_BREACH": f"每週流動資產 = {risk_result.get('weekly_liquid_pct', 'N/A'):.2f}%，低於 15% 下限（第8.2(n)條）",
            "SINGLE_ENTITY_BREACH": "單一實體集中度超過 10% 上限（第8.2(g)條）",
            "GROUP_BREACH": "同集團集中度超過 20% 上限（第8.2(g)(a)條）",
        }
        for flag in breach_flags:
            lines.append(f"  • {flag_map.get(flag, flag)}")
        lines.extend(["", "如批准：生成合規報告並標注違規，等待進一步修正措施。"])
        return "\n".join(lines)

    def _abort(self, task_id: str, reason: str) -> dict:
        self._log(task_id, "TASK_ABORTED", {"reason": reason})
        return {"task_id": task_id, "status": "aborted", "reason": reason}

    def _log(self, task_id: str, event: str, data: dict) -> None:
        entry = {"task_id": task_id, "event": event, "data": data, "ts": datetime.utcnow().isoformat()}
        self.task_log.append(entry)
        logger.info("[%s] %s: %s", task_id[:8], event, json.dumps(data, ensure_ascii=False)[:200])


# ─── CLI 入口 ─────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="ARISK Agent Orchestrator")
    parser.add_argument("fund_id", help="基金 ID")
    parser.add_argument("as_of_date", help="日期 YYYY-MM-DD")
    parser.add_argument("--skip-review", action="store_true", help="跳過人工審核（僅測試用）")
    parser.add_argument("--risk-only", action="store_true", help="只執行到 risk-calculator（巡檢模式）")
    args = parser.parse_args()

    orch = RiskAgentOrchestrator()
    result = await orch.run(
        args.fund_id,
        args.as_of_date,
        skip_review=args.skip_review,
        risk_only=args.risk_only,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
