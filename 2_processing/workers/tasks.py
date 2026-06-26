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
    from 2_processing.api.deps import AsyncSessionLocal
    from 2_processing.risk.exposure_engine import compute_exposure

    target_date = date.fromisoformat(as_of_date) if as_of_date else date.today() - timedelta(days=1)

    async def _run():
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
