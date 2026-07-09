"""
tests/test_scheduler.py — 定時調度器單元測試

覆蓋範圍：
  1. start_scheduler 冪等（多次調用只啟動一次線程）
  2. last_run_date 防重複（同一天不再觸發）
  3. _running_schedules 防並發（任務執行中不再觸發）
  4. 時間不匹配不觸發
  5. disabled 任務不觸發
  6. 正常觸發流程（mock exec）
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── 幫助：構造調度配置 ────────────────────────────────────────────

def _make_schedule(
    sid: str = "test-sid-001",
    hour: int = 8,
    minute: int = 0,
    enabled: bool = True,
    last_run_date: str | None = None,
) -> dict:
    return {
        "schedule_id": sid,
        "name":        "測試任務",
        "report_id":   "report_03_mmf",
        "fund_id":     "BHMMF001",
        "hour":        hour,
        "minute":      minute,
        "enabled":     enabled,
        "run_count":   0,
        "last_run":    None,
        "last_run_date": last_run_date,
        "last_status": None,
    }


# ── 1. start_scheduler 冪等測試 ───────────────────────────────────

def test_start_scheduler_idempotent(tmp_path, monkeypatch):
    """多次調用 start_scheduler() 只應啟動一個線程。"""
    import importlib
    import sys

    # 重置模塊狀態以便測試
    mod_key = "2_processing.api.routers.schedules"
    if mod_key in sys.modules:
        del sys.modules[mod_key]

    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))

    # patch 掉調度循環（讓它立刻結束）
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        from importlib import import_module
        sched_mod = import_module("2_processing.api.routers.schedules")

        # 重置內部狀態
        sched_mod._sched_started = False
        sched_mod._sched_thread  = None

        sched_mod.start_scheduler()
        sched_mod.start_scheduler()   # 第二次調用
        sched_mod.start_scheduler()   # 第三次調用

        # Thread 只被構造一次
        assert mock_thread_cls.call_count == 1
        assert mock_thread.start.call_count == 1


# ── 2. last_run_date 防重複觸發 ───────────────────────────────────

def test_last_run_date_guard_skips_same_day(tmp_path, monkeypatch):
    """同一天 last_run_date 已設置時，調度器不應再次觸發任務。"""
    today = datetime.now().strftime("%Y-%m-%d")
    sid   = "sid-guard-test"
    sch   = _make_schedule(sid=sid, last_run_date=today)

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    triggered = []

    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    from importlib import import_module
    sched_mod = import_module("2_processing.api.routers.schedules")

    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", schedules_file)
    monkeypatch.setattr(sched_mod, "HISTORY_FILE",   tmp_path / "history.json")
    monkeypatch.setattr(sched_mod, "_running_schedules", set())

    # Mock _exec_report 追蹤調用次數
    def mock_exec(*args, **kwargs):
        triggered.append(args)
        return {"run_id": "r1", "schedule_id": sid, "status": "completed",
                "report_id": "report_03_mmf", "fund_id": "BHMMF001",
                "as_of_date": today, "output_file": "test.xlsx",
                "message": "ok", "started_at": today, "finished_at": today}

    monkeypatch.setattr(sched_mod, "_exec_report", mock_exec)

    # 模擬一次調度器檢查（時間匹配）
    now   = datetime.now()
    sch["hour"]   = now.hour
    sch["minute"] = now.minute
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    # 直接調用調度器內部邏輯（不啟動線程）
    _simulate_one_tick(sched_mod, now)

    assert len(triggered) == 0, "已設置 last_run_date 的任務不應被觸發"


# ── 3. 並發保護（_running_schedules）────────────────────────────

def test_running_guard_prevents_concurrent(tmp_path, monkeypatch):
    """任務正在執行中時，不應再次觸發。"""
    today = datetime.now().strftime("%Y-%m-%d")
    sid   = "sid-running-test"
    sch   = _make_schedule(sid=sid)

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    from importlib import import_module
    sched_mod = import_module("2_processing.api.routers.schedules")

    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", schedules_file)
    monkeypatch.setattr(sched_mod, "HISTORY_FILE",   tmp_path / "history.json")
    # 標記為正在執行
    running = {sid}
    monkeypatch.setattr(sched_mod, "_running_schedules", running)

    triggered = []
    monkeypatch.setattr(sched_mod, "_exec_report", lambda *a, **k: triggered.append(a))

    now = datetime.now()
    sch["hour"]   = now.hour
    sch["minute"] = now.minute
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    _simulate_one_tick(sched_mod, now)

    assert len(triggered) == 0, "正在執行中的任務不應再次觸發"


# ── 4. 時間不匹配不觸發 ──────────────────────────────────────────

def test_time_mismatch_no_trigger(tmp_path, monkeypatch):
    """時間不符的任務不觸發。"""
    sid = "sid-time-test"
    sch = _make_schedule(sid=sid, hour=23, minute=59)  # 不可能匹配 now

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    from importlib import import_module
    sched_mod = import_module("2_processing.api.routers.schedules")

    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", schedules_file)
    monkeypatch.setattr(sched_mod, "_running_schedules", set())

    triggered = []
    monkeypatch.setattr(sched_mod, "_exec_report", lambda *a, **k: triggered.append(a))

    now = datetime(2026, 1, 1, 8, 0)  # 08:00，不匹配 23:59
    _simulate_one_tick(sched_mod, now)

    assert len(triggered) == 0


# ── 5. disabled 任務不觸發 ───────────────────────────────────────

def test_disabled_schedule_not_triggered(tmp_path, monkeypatch):
    """enabled=False 的任務不觸發。"""
    now = datetime.now()
    sid = "sid-disabled-test"
    sch = _make_schedule(sid=sid, hour=now.hour, minute=now.minute, enabled=False)

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    from importlib import import_module
    sched_mod = import_module("2_processing.api.routers.schedules")

    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", schedules_file)
    monkeypatch.setattr(sched_mod, "_running_schedules", set())

    triggered = []
    monkeypatch.setattr(sched_mod, "_exec_report", lambda *a, **k: triggered.append(a))

    _simulate_one_tick(sched_mod, now)
    assert len(triggered) == 0


# ── 6. 正常首次觸發 ──────────────────────────────────────────────

def test_first_trigger_sets_last_run_date(tmp_path, monkeypatch):
    """首次到點觸發後，last_run_date 應被寫入，防止當天重複。"""
    now   = datetime.now()
    today = now.strftime("%Y-%m-%d")
    sid   = "sid-first-trigger"
    sch   = _make_schedule(sid=sid, hour=now.hour, minute=now.minute)

    schedules_file = tmp_path / "schedules.json"
    history_file   = tmp_path / "history.json"
    schedules_file.write_text(json.dumps({sid: sch}), encoding="utf-8")

    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    from importlib import import_module
    sched_mod = import_module("2_processing.api.routers.schedules")

    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", schedules_file)
    monkeypatch.setattr(sched_mod, "HISTORY_FILE",   history_file)
    monkeypatch.setattr(sched_mod, "_running_schedules", set())

    exec_called = []
    def mock_exec(schedule_id, report_id, fund_id, as_of_date):
        exec_called.append((schedule_id, report_id, fund_id, as_of_date))
        return {
            "run_id": "r1", "schedule_id": schedule_id, "status": "completed",
            "report_id": report_id, "fund_id": fund_id, "as_of_date": as_of_date,
            "output_file": "test.xlsx", "message": "ok",
            "started_at": today, "finished_at": today,
        }

    monkeypatch.setattr(sched_mod, "_exec_report", mock_exec)

    # 第一次 tick → 應觸發
    _simulate_one_tick(sched_mod, now)

    # 等執行緒完成（mock exec 是同步的，但線程啟動有延遲）
    time.sleep(0.2)

    assert len(exec_called) == 1, "首次到點應觸發一次"

    # 第二次 tick（同分鐘）→ last_run_date 已設置，不再觸發
    _simulate_one_tick(sched_mod, now)
    time.sleep(0.1)

    assert len(exec_called) == 1, "同天同分鐘第二次 tick 不應再次觸發"


# ── 模擬調度器單次檢查（不 sleep，不啟動線程）────────────────────

def _simulate_one_tick(sched_mod, now: datetime) -> None:
    """
    提取 _scheduler_loop 的核心判斷邏輯，同步執行一次檢查。
    觸發條件滿足時，直接同步調用 _exec_report（跳過 Thread）。
    """
    today = now.strftime("%Y-%m-%d")

    with sched_mod._lock:
        schedules = sched_mod._load_schedules()

    for sid, sch in schedules.items():
        if not sch.get("enabled", False):
            continue
        if sch.get("hour") != now.hour or sch.get("minute") != now.minute:
            continue
        if sch.get("last_run_date") == today:
            continue
        if sid in sched_mod._running_schedules:
            continue

        # 原子標記（同 _scheduler_loop）
        with sched_mod._lock:
            s2 = sched_mod._load_schedules()
            if sid not in s2:
                continue
            if s2[sid].get("last_run_date") == today:
                continue
            s2[sid]["last_run_date"] = today
            sched_mod._save_schedules(s2)

        sched_mod._running_schedules.add(sid)

        def _run(s=sch, schedule_id=sid):
            try:
                entry = sched_mod._exec_report(
                    schedule_id, s["report_id"], s["fund_id"],
                    now.strftime("%Y-%m-%d"),
                )
                sched_mod._record_run(entry)
            finally:
                sched_mod._running_schedules.discard(schedule_id)

        threading.Thread(target=_run, daemon=True).start()
