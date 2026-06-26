"""Celery 應用：定期風控計算、ETL 任務。"""
from __future__ import annotations

import os
from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

app = Celery(
    "fsi_risk_workers",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["2_processing.workers.tasks"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Hong_Kong",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

# 定時任務
app.conf.beat_schedule = {
    # 每個交易日 18:30 執行風控快照計算
    "daily-risk-snapshot": {
        "task": "2_processing.workers.tasks.compute_daily_risk_snapshot",
        "schedule": crontab(hour=18, minute=30, day_of_week="mon-fri"),
        "kwargs": {"fund_ids": []},  # 空列表表示所有基金
    },
    # 每小時更新 Redis 行情緩存
    "refresh-price-cache": {
        "task": "2_processing.workers.tasks.refresh_price_cache",
        "schedule": crontab(minute=0),
    },
    # 每個交易日 09:00 載入昨日持倉
    "load-daily-positions": {
        "task": "2_processing.workers.tasks.load_daily_positions",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon-fri"),
    },
}
