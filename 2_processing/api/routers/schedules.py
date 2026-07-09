"""定時報表排程路由 — 管理定時任務、背景執行、歷史記錄。

架構：
  - 配置持久化：artefacts/schedules.json
  - 歷史記錄：  artefacts/schedules_history.json
  - 背景調度：  獨立 daemon 線程，每分鐘檢查一次是否有任務到期
  - 輸出目錄：  artefacts/scheduled/<schedule_id>/
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_api_key)])

# ── 路徑 ──────────────────────────────────────────────────────────
REPO_ROOT      = Path(__file__).parent.parent.parent.parent
TOOLS_MMF      = REPO_ROOT / "2_processing" / "tools" / "mmf"
SQL_MMF        = REPO_ROOT / "2_processing" / "sql" / "mmf"
ARTEFACTS      = REPO_ROOT / "artefacts"
SCHEDULED_ROOT = ARTEFACTS / "scheduled"
SCHEDULES_FILE = ARTEFACTS / "schedules.json"
HISTORY_FILE   = ARTEFACTS / "schedules_history.json"

SCHEDULED_ROOT.mkdir(parents=True, exist_ok=True)

# ── 報表定義（與 reports.py 保持一致） ───────────────────────────
REPORT_DEFS = {
    "report_03_mmf": {
        "name": "MMF 日報（SFC 合規版）",
        "script": str(TOOLS_MMF / "run_report.py"),
        "args_fn": lambda fid, dt: ["--report", "report_03_mmf", "--port", fid, "--date", dt],
        "suffix": ".xlsx",
    },
    "report_04_mmf_monthly": {
        "name": "MMF 月報 Factsheet",
        "script": str(TOOLS_MMF / "report_04" / "run_monthly.py"),
        "args_fn": lambda fid, dt: ["--date", dt],
        "suffix": ".docx",
    },
    "report_06": {
        "name": "基金詳細分析報告",
        "script": str(TOOLS_MMF / "run_report.py"),
        "args_fn": lambda fid, dt: ["--report", "report_06", "--port", fid, "--date", dt],
        "suffix": ".xlsx",
    },
}

FUNDS = {
    "BHMMF001": "博匯港元貨幣市場基金 I",
    "BHMMF002": "博匯港元貨幣市場基金 II",
}

# ── JSON 持久化 ───────────────────────────────────────────────────
_lock = threading.Lock()

def _load_schedules() -> dict[str, dict]:
    if SCHEDULES_FILE.exists():
        try:
            return json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_schedules(data: dict) -> None:
    SCHEDULES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_history(data: list) -> None:
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 報表執行（同步，在線程中調用） ────────────────────────────────
def _exec_report(schedule_id: str, report_id: str, fund_id: str, as_of_date: str) -> dict:
    """執行一次報表生成，返回歷史記錄條目。"""
    defn = REPORT_DEFS[report_id]
    dest_dir = SCHEDULED_ROOT / schedule_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_dir = SQL_MMF / "output" / report_id
    src_dir.mkdir(parents=True, exist_ok=True)

    run_id    = str(uuid.uuid4())
    started   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")   # 本地時間
    date_str  = as_of_date.replace("-", "")

    cmd = [sys.executable, defn["script"]] + defn["args_fn"](fund_id, as_of_date)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONUTF8"] = "1"

    try:
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            env=env, cwd=str(REPO_ROOT), timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"腳本返回碼 {result.returncode}: {(result.stderr or '')[-300:]}")

        candidates = sorted(
            [f for f in src_dir.iterdir() if f.suffix == defn["suffix"] and date_str in f.name],
            key=lambda f: f.stat().st_mtime, reverse=True,
        )
        if not candidates:
            raise RuntimeError(f"腳本執行成功但未找到輸出文件（{date_str}*{defn['suffix']}）")

        src = candidates[0]
        import shutil
        dest = dest_dir / src.name
        shutil.copy2(src, dest)

        logger.info("[schedule] completed %s -> %s", schedule_id, dest.name)
        return {
            "run_id": run_id, "schedule_id": schedule_id, "report_id": report_id,
            "fund_id": fund_id, "as_of_date": as_of_date,
            "status": "completed", "output_file": src.name,
            "message": f"生成完成：{src.name}",
            "started_at": started, "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        msg = str(exc)[:400]
        logger.error("[schedule] failed %s: %s", schedule_id, msg, exc_info=True)
        return {
            "run_id": run_id, "schedule_id": schedule_id, "report_id": report_id,
            "fund_id": fund_id, "as_of_date": as_of_date,
            "status": "failed", "output_file": None,
            "message": msg,
            "started_at": started, "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def _record_run(entry: dict) -> None:
    with _lock:
        hist = _load_history()
        hist.insert(0, entry)
        hist = hist[:500]          # 最多保留 500 條歷史
        _save_history(hist)

        # 更新 schedule 的 last_run / run_count
        schedules = _load_schedules()
        sid = entry["schedule_id"]
        if sid in schedules:
            schedules[sid]["last_run"]    = entry["started_at"]
            schedules[sid]["last_status"] = entry["status"]
            schedules[sid]["run_count"]   = schedules[sid].get("run_count", 0) + 1
        _save_schedules(schedules)


# ── 「正在執行」集合：防止同一排程並發執行 ──────────────────────
_running_schedules: set[str] = set()


# ── 背景調度線程 ──────────────────────────────────────────────────
def _scheduler_loop() -> None:
    """
    每分鐘整點檢查是否有定時任務到期。

    防雙觸機制（三層）：
      1. last_run_date（本地日期）：同一天只執行一次
      2. _running_schedules：當前正在執行中的任務不重複啟動
      3. sleep 對齊到下一個整分鐘：避免同分鐘內多次喚醒
    """
    logger.info("[scheduler] background scheduler started (local time)")
    while True:
        try:
            now   = datetime.now()
            today = now.strftime("%Y-%m-%d")   # 本地日期

            with _lock:
                schedules = _load_schedules()

            for sid, sch in schedules.items():
                if not sch.get("enabled", False):
                    continue
                # 時間匹配（24 小時制本地時間）
                if sch.get("hour") != now.hour or sch.get("minute") != now.minute:
                    continue
                # 今天已執行（last_run_date 用本地日期）
                if sch.get("last_run_date") == today:
                    logger.debug("[scheduler] skip %s: already ran today (%s)", sid, today)
                    continue
                # 正在執行中（防止慢速任務被再次觸發）
                if sid in _running_schedules:
                    logger.warning("[scheduler] skip %s: still running", sid)
                    continue

                # 原子標記：今日已執行 + 加入執行中集合
                with _lock:
                    schedules2 = _load_schedules()
                    if sid not in schedules2:
                        continue
                    # 二次確認（防 file-reload 後 last_run_date 已被其他線程設置）
                    if schedules2[sid].get("last_run_date") == today:
                        continue
                    schedules2[sid]["last_run_date"] = today
                    _save_schedules(schedules2)
                _running_schedules.add(sid)

                def _run(s=sch, schedule_id=sid, run_date=today):
                    try:
                        entry = _exec_report(
                            schedule_id,
                            s["report_id"],
                            s["fund_id"],
                            date.today().strftime("%Y-%m-%d"),
                        )
                        _record_run(entry)
                    finally:
                        _running_schedules.discard(schedule_id)

                threading.Thread(target=_run, daemon=True, name=f"sched-{sid[:8]}").start()
                logger.info("[scheduler] triggered %s (%s) at %s",
                            sid[:8], sch.get("name"), now.strftime("%H:%M"))

        except Exception:
            logger.exception("[scheduler] loop error")

        # 對齊到下一個整分鐘（避免同分鐘內多次觸發）
        now     = datetime.now()
        seconds = now.second + now.microsecond / 1_000_000
        sleep_s = max(60 - seconds, 1)   # 等到下一個整分鐘
        time.sleep(sleep_s)


# ── 調度器啟動（由 lifespan 調用，避免 uvicorn reload 雙進程雙啟）────
_sched_thread:   threading.Thread | None = None
_sched_started  = False
_sched_start_lk = threading.Lock()


def start_scheduler() -> None:
    """啟動後台調度線程。冪等：多次調用只啟動一次。"""
    global _sched_thread, _sched_started
    with _sched_start_lk:
        if _sched_started:
            logger.info("[scheduler] already running, skip duplicate start")
            return
        _sched_thread = threading.Thread(
            target=_scheduler_loop, daemon=True, name="report-scheduler"
        )
        _sched_thread.start()
        _sched_started = True
        logger.info("[scheduler] background scheduler started (pid=%d)", os.getpid())


# ── Pydantic 模型 ─────────────────────────────────────────────────
class ScheduleCreate(BaseModel):
    name:      str
    report_id: str
    fund_id:   str
    hour:      int   # 0-23
    minute:    int   # 0-59
    enabled:   bool = True


class ScheduleUpdate(BaseModel):
    name:      str   | None = None
    report_id: str   | None = None
    fund_id:   str   | None = None
    hour:      int   | None = None
    minute:    int   | None = None
    enabled:   bool  | None = None


# ── API Endpoints ─────────────────────────────────────────────────

@router.get("/", summary="查詢所有定時任務")
def list_schedules():
    with _lock:
        schedules = _load_schedules()
    return list(schedules.values())


@router.post("/", summary="新建定時任務")
def create_schedule(req: ScheduleCreate):
    if req.report_id not in REPORT_DEFS:
        raise HTTPException(400, f"未知報表 ID：{req.report_id}")
    if req.fund_id not in FUNDS:
        raise HTTPException(400, f"未知基金 ID：{req.fund_id}")
    if not (0 <= req.hour <= 23 and 0 <= req.minute <= 59):
        raise HTTPException(400, "hour 須 0-23，minute 須 0-59")

    sid = str(uuid.uuid4())
    entry = {
        "schedule_id":   sid,
        "name":          req.name,
        "report_id":     req.report_id,
        "report_name":   REPORT_DEFS[req.report_id]["name"],
        "fund_id":       req.fund_id,
        "fund_name":     FUNDS[req.fund_id],
        "hour":          req.hour,
        "minute":        req.minute,
        "enabled":       req.enabled,
        "run_count":     0,
        "last_run":      None,
        "last_run_date": None,
        "last_status":   None,
        "created_at":    datetime.utcnow().isoformat(),
    }
    with _lock:
        schedules = _load_schedules()
        schedules[sid] = entry
        _save_schedules(schedules)
    return entry


@router.patch("/{schedule_id}", summary="更新定時任務")
def update_schedule(schedule_id: str, req: ScheduleUpdate):
    with _lock:
        schedules = _load_schedules()
        if schedule_id not in schedules:
            raise HTTPException(404, "任務不存在")
        sch = schedules[schedule_id]
        for field, val in req.model_dump(exclude_none=True).items():
            if field == "report_id" and val not in REPORT_DEFS:
                raise HTTPException(400, f"未知報表 ID：{val}")
            if field == "fund_id" and val not in FUNDS:
                raise HTTPException(400, f"未知基金 ID：{val}")
            sch[field] = val
        # 同步冗余字段
        if "report_id" in req.model_dump(exclude_none=True):
            sch["report_name"] = REPORT_DEFS[sch["report_id"]]["name"]
        if "fund_id" in req.model_dump(exclude_none=True):
            sch["fund_name"] = FUNDS[sch["fund_id"]]
        sch["last_run_date"] = None  # 修改後允許今日再次執行
        schedules[schedule_id] = sch
        _save_schedules(schedules)
    return sch


@router.delete("/{schedule_id}", summary="刪除定時任務")
def delete_schedule(schedule_id: str):
    with _lock:
        schedules = _load_schedules()
        if schedule_id not in schedules:
            raise HTTPException(404, "任務不存在")
        del schedules[schedule_id]
        _save_schedules(schedules)
    return {"deleted": schedule_id}


@router.post("/{schedule_id}/run-now", summary="立即執行一次")
def run_now(schedule_id: str):
    """立即執行，使用今日日期，結果計入歷史。"""
    with _lock:
        schedules = _load_schedules()
    if schedule_id not in schedules:
        raise HTTPException(404, "任務不存在")
    sch = schedules[schedule_id]

    if schedule_id in _running_schedules:
        raise HTTPException(409, f"任務 {sch['name']} 正在執行中，請稍後再試")

    _running_schedules.add(schedule_id)

    def _run():
        try:
            entry = _exec_report(
                schedule_id, sch["report_id"], sch["fund_id"],
                date.today().strftime("%Y-%m-%d"),
            )
            _record_run(entry)
        finally:
            _running_schedules.discard(schedule_id)

    threading.Thread(target=_run, daemon=True, name=f"runnow-{schedule_id[:8]}").start()
    return {"message": f"任務 {sch['name']} 已開始執行"}


@router.get("/history/all", summary="查詢所有歷史記錄")
def get_all_history(limit: int = 100):
    return _load_history()[:limit]


@router.delete("/history/{run_id}", summary="刪除單條歷史記錄")
def delete_history_entry(run_id: str):
    with _lock:
        hist = _load_history()
        filtered = [h for h in hist if h.get("run_id") != run_id]
        if len(filtered) == len(hist):
            raise HTTPException(404, f"歷史記錄不存在：{run_id}")
        _save_history(filtered)
    return {"deleted": run_id}


@router.get("/{schedule_id}/history", summary="查詢單個任務歷史")
def get_schedule_history(schedule_id: str, limit: int = 50):
    hist = _load_history()
    return [h for h in hist if h.get("schedule_id") == schedule_id][:limit]


@router.get("/{schedule_id}/files", summary="查詢已生成文件列表")
def list_files(schedule_id: str):
    dest_dir = SCHEDULED_ROOT / schedule_id
    if not dest_dir.exists():
        return []
    files = sorted(dest_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "size_kb":  round(f.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in files if f.is_file()
    ]


@router.get("/{schedule_id}/download/{filename}", summary="下載歷史文件")
def download_file(schedule_id: str, filename: str):
    dest_dir = SCHEDULED_ROOT / schedule_id
    file_path = dest_dir / filename
    if not file_path.exists():
        raise HTTPException(404, f"文件不存在：{filename}")
    try:
        file_path.resolve().relative_to(dest_dir.resolve())
    except ValueError:
        raise HTTPException(403, "非法路徑")
    media = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf":  "application/pdf",
    }.get(file_path.suffix, "application/octet-stream")
    return FileResponse(path=str(file_path), filename=filename, media_type=media)
