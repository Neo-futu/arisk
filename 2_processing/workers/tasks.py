"""Celery 任務定義。"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from .celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在同步 Celery 任務中運行異步代碼。"""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def compute_daily_risk_snapshot(self, fund_ids: list[str] | None = None, as_of_date: str | None = None):
    """計算並持久化每日風控快照。"""
    target_date = date.fromisoformat(as_of_date) if as_of_date else date.today() - timedelta(days=1)

    async def _run():
        import sys, importlib
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        deps_mod    = importlib.import_module("2_processing.api.deps")
        risk_mod    = importlib.import_module("2_processing.tools.risk.exposure_engine")
        AsyncSessionLocal = deps_mod.AsyncSessionLocal
        compute_exposure  = risk_mod.compute_exposure

        async with AsyncSessionLocal() as db:
            if not fund_ids:
                from sqlalchemy import text
                rows = await db.execute(text("SELECT fund_id FROM fsi.funds WHERE is_active"))
                ids = [r[0] for r in rows]
            else:
                ids = fund_ids

            results = []
            for fid in ids:
                try:
                    exposure = await compute_exposure(fid, target_date, db)
                    # 保存快照
                    await db.execute(
                        text("""
                            INSERT INTO fsi.risk_snapshots (
                                fund_id, as_of_date, total_nav_hkd,
                                wam_days, wal_days, daily_liquid_pct, weekly_liquid_pct,
                                is_compliant, breach_flags
                            ) VALUES (
                                :fid, :dt, :nav, :wam, :wal, :dliq, :wliq, :comp, :flags
                            )
                            ON CONFLICT (fund_id, as_of_date) DO UPDATE
                            SET wam_days = EXCLUDED.wam_days,
                                wal_days = EXCLUDED.wal_days,
                                is_compliant = EXCLUDED.is_compliant,
                                breach_flags = EXCLUDED.breach_flags,
                                calc_ts = NOW()
                        """),
                        {
                            "fid": fid, "dt": target_date,
                            "nav": exposure.total_nav_hkd,
                            "wam": exposure.wam_days, "wal": exposure.wal_days,
                            "dliq": exposure.daily_liquid_pct, "wliq": exposure.weekly_liquid_pct,
                            "comp": exposure.is_compliant,
                            "flags": str(exposure.breach_flags),
                        },
                    )
                    await db.commit()
                    results.append({"fund_id": fid, "status": "ok"})
                    logger.info("Risk snapshot computed for %s on %s", fid, target_date)
                except Exception as exc:
                    logger.error("Failed to compute risk for %s: %s", fid, exc)
                    results.append({"fund_id": fid, "status": "error", "error": str(exc)})
            return results

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task
def refresh_price_cache():
    """刷新 Redis 中的市場行情緩存（從 WindAPI 拉取）。"""
    logger.info("Refreshing price cache from WindAPI")
    # TODO: 調用 4_mcp/wind/ 模組拉取最新行情
    return {"status": "refreshed"}


@app.task
def load_daily_positions():
    """從持倉文件或 Wind 載入昨日持倉快照。"""
    logger.info("Loading daily positions")
    # TODO: 調用 2_processing/etl/load_positions.py
    return {"status": "loaded"}


# ── Layer 4: AI Agent 異步任務（Celery 統一編排） ──────────────────

@app.task(bind=True, max_retries=2, default_retry_delay=30, time_limit=600)
def run_agent_task(
    self,
    task_id:    str,
    agent_name: str,
    model_id:   str,
    messages:   list[dict],
    context:    dict | None = None,
    session_id: str | None = None,
    user_id:    str | None = None,
):
    """
    Layer 4 — Celery AI Agent 任務（持久化 + 重試 + 超時控制）。

    用於需要較長時間的 AI 分析任務（>30s）。
    結果通過 Redis TaskState 存儲，可通過 GET /agent/v2/task/{id} 查詢。

    優勢（相比 asyncio.create_task）：
      - 任務持久化：Worker 重啟不丟失
      - 自動重試：失敗後最多重試 2 次
      - 超時控制：最長 600 秒
      - 可監控：通過 Celery Flower / Redis 追蹤
    """
    import sys, os
    from pathlib import Path
    REPO_ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(REPO_ROOT))

    async def _run():
        from aiagent.orchestrator.task_state import TaskState, TaskStatus
        from aiagent.engine.runner import run_agent

        # 加載 Redis 任務狀態
        ts = await TaskState.load(task_id)
        if not ts:
            # 重新創建（Worker 重啟後 task_id 可能還有效）
            from aiagent.orchestrator.task_state import TaskState as TS
            ts = await TS.create(agent_id=agent_name, query="", model_id=model_id,
                                 session_id=session_id, user_id=user_id)

        try:
            await ts.transition(TaskStatus.EXECUTING)
            await ts.log(f"Celery Worker 開始執行: agent={agent_name}, model={model_id}")

            result_parts: list[str] = []
            tool_calls: list[dict] = []

            async for event in run_agent(
                messages=messages,
                agent_name=agent_name,
                context=context,
                model=model_id,
                session_id=session_id,
                user_id=user_id,
            ):
                if event.get("type") == "text":
                    result_parts.append(event.get("content", ""))
                elif event.get("type") == "tool_call":
                    tool_calls.append({"name": event.get("name"), "input": event.get("input")})
                    await ts.log(f"工具調用: {event.get('name')}")
                elif event.get("type") == "error":
                    await ts.fail(event.get("message", "未知錯誤"))
                    return {"status": "failed", "error": event.get("message")}

            await ts.transition(TaskStatus.REFLECTING)
            result = {
                "reply":      "".join(result_parts),
                "tool_calls": tool_calls,
                "agent":      agent_name,
                "model":      model_id,
            }
            await ts.complete(result)
            await ts.log("Celery 任務成功完成")
            return result

        except Exception as exc:
            error_msg = str(exc)[:300]
            await ts.fail(error_msg)
            logger.error("[celery] run_agent_task failed: %s", exc)
            raise

    try:
        return _run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=1, time_limit=300)
def run_ai_anomaly_detection(self, fund_id: str, as_of_date: str):
    """
    Layer 1+4 — AI 驅動的風控異常檢測（Celery + AI）。

    在每日風控快照完成後觸發，讓 AI 分析數據是否有異常：
      - WAM/WAL 接近上限
      - 流動性比率突變
      - 持倉集中度超標

    結果存儲到 iam.agent_episode（情景記憶），可在下次對話中參考。
    """
    import sys, os
    from pathlib import Path
    REPO_ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(REPO_ROOT))

    async def _run():
        from aiagent.engine.runner import run_agent

        query = (
            f"請分析 {fund_id} 在 {as_of_date} 的風控數據是否存在異常或需要關注的信號。"
            "如發現任何指標接近監管閾值或出現突變，請明確指出。"
        )
        messages = [{"role": "user", "content": query}]

        parts: list[str] = []
        async for event in run_agent(
            messages=messages,
            agent_name="risk-analyst",
            model=None,  # 使用默認模型
        ):
            if event.get("type") == "text":
                parts.append(event.get("content", ""))

        analysis = "".join(parts)
        logger.info("[AI Anomaly] %s %s: %s...", fund_id, as_of_date, analysis[:100])
        return {"fund_id": fund_id, "as_of_date": as_of_date, "analysis": analysis}

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("[celery] ai_anomaly_detection failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200]}
