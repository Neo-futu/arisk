"""報表生成路由 — 觸發後台生成任務、查詢進度、下載文件。

架構：
  - 任務執行：ThreadPoolExecutor + subprocess.run（兼容 Windows/uvicorn）
  - 輸出目錄：artefacts/reports/<report_id>/（統一輸出，方便校驗和下載）
  - 任務狀態：內存 dict（生產可替換為 Redis）
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_api_key)])

# ── 路徑 ──────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent.parent.parent   # fsi-risk-platform/
TOOLS_MMF    = REPO_ROOT / "2_processing" / "tools" / "mmf"
SQL_MMF      = REPO_ROOT / "2_processing" / "sql" / "mmf"
REPORTS_ROOT = REPO_ROOT / "artefacts" / "reports"          # 統一輸出目錄

# ── 線程池（最多 4 個並發生成任務） ──────────────────────────────
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="report")

# ── 任務狀態存儲 ──────────────────────────────────────────────────
_tasks: dict[str, dict] = {}


# ── fund_id → 基金全名（run_monthly.py 用 --fund 傳完整中文名） ──
FUND_NAMES: dict[str, str] = {
    "BHMMF001": "博匯港元貨幣市場基金I",
    "BHMMF002": "博匯港元貨幣市場基金II",
}

# ── 報表定義 ──────────────────────────────────────────────────────
def _report_03_args(port_id: str, ev_date: str) -> list[str]:
    return ["--report", "report_03_mmf", "--port", port_id, "--date", ev_date]

def _report_04_args(port_id: str, ev_date: str) -> list[str]:
    """使用 --port-id（ASCII）傳遞基金標識，避免 Windows shell 中文編碼問題。"""
    args = ["--date", ev_date]
    if port_id:
        args += ["--port-id", port_id]
    return args

def _report_06_args(port_id: str, ev_date: str) -> list[str]:
    return ["--report", "report_06", "--port", port_id, "--date", ev_date]

REPORT_DEFS: dict[str, dict] = {
    "report_03_mmf": {
        "name":     "MMF 日報（SFC 合規版）",
        "script":   str(TOOLS_MMF / "run_report.py"),
        "args_fn":  _report_03_args,
        "suffixes": [".xlsx"],          # 搜索優先級列表
    },
    "report_04_mmf_monthly": {
        "name":     "MMF 月報 Factsheet",
        "script":   str(TOOLS_MMF / "report_04" / "run_monthly.py"),
        "args_fn":  _report_04_args,
        "suffixes": [".docx", ".xlsx"], # 先找 Word，沒有就返回 XLSX
    },
    "report_06": {
        "name":     "基金詳細分析報告",
        "script":   str(TOOLS_MMF / "run_report.py"),
        "args_fn":  _report_06_args,
        "suffixes": [".xlsx"],
    },
}

# 向後兼容：若定義只有 "suffix" 字段，統一轉為 "suffixes" 列表
for _d in REPORT_DEFS.values():
    if "suffix" in _d and "suffixes" not in _d:
        _d["suffixes"] = [_d["suffix"]]


# ── 同步執行（線程池中運行） ──────────────────────────────────────
def _run_report_sync(task_id: str, report_id: str, fund_id: str, as_of_date: str) -> None:
    task = _tasks[task_id]
    defn = REPORT_DEFS[report_id]

    # 輸出目錄（腳本使用 SQL_MMF/output，生成後複製/移動到 artefacts/reports）
    src_output_dir  = SQL_MMF / "output" / report_id
    dest_output_dir = REPORTS_ROOT / report_id
    src_output_dir.mkdir(parents=True, exist_ok=True)
    dest_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        task["status"]   = "running"
        task["progress"] = 10
        task["message"]  = "啟動報表生成腳本..."

        cmd = [sys.executable, defn["script"]] + defn["args_fn"](fund_id, as_of_date)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        env["PYTHONUTF8"] = "1"

        logger.info("[report] cmd: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(REPO_ROOT),
            timeout=300,
        )

        task["progress"] = 70
        stdout_tail = (result.stdout or "")[-600:]
        stderr_tail = (result.stderr or "")[-400:]
        combined    = (stdout_tail + "\n" + stderr_tail).strip()

        logger.info("[report] returncode=%d  stdout_tail=%s", result.returncode, stdout_tail[:200])

        if result.returncode != 0:
            raise RuntimeError(
                f"腳本返回碼 {result.returncode}。\n{combined[-300:]}"
            )

        task["progress"] = 80
        task["message"]  = "複製輸出文件到 artefacts/..."

        # 收集所有生成的輸出文件（xlsx + docx + pdf）
        # xlsx 不含基金名（全基金匯總），docx/pdf 用基金名精確過濾避免混入其他基金文件
        import shutil
        date_str    = as_of_date.replace("-", "")
        fund_name   = FUND_NAMES.get(fund_id, "")   # 用於 docx/pdf 精確過濾
        output_files: list[str] = []

        for sfx, use_fund_filter in [(".xlsx", False), (".docx", True), (".pdf", True)]:
            candidates = sorted(
                [f for f in src_output_dir.iterdir()
                 if f.suffix == sfx and date_str in f.name and f.is_file()],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if use_fund_filter and fund_name:
                # docx/pdf 精確匹配基金名（文件名以基金名結尾，避免 I 匹配 II）
                candidates = [f for f in candidates if f.stem.endswith(fund_name)]
            for src_file in candidates:
                dest_file = dest_output_dir / src_file.name
                shutil.copy2(src_file, dest_file)
                if src_file.name not in output_files:
                    output_files.append(src_file.name)

        if not output_files:
            existing = [
                f"{f.stat().st_size//1024} KB {f.name}"
                for f in sorted(src_output_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
                if f.is_file()
            ][:5]
            existing_str = "  ".join(existing) or "（目錄為空）"
            raise RuntimeError(
                f"腳本執行成功但找不到任何輸出文件（xlsx/docx/pdf）。\n"
                f"搜索日期：{date_str}  目錄現有：{existing_str}\n"
                f"請確認所選日期在數據庫中有對應數據。"
            )

        # 主文件：優先 docx > xlsx（用於舊 output_file 字段兼容）
        primary = next(
            (f for sfx in [".docx", ".pdf", ".xlsx"] for f in output_files if f.endswith(sfx)),
            output_files[0],
        )

        task.update({
            "status":       "completed",
            "progress":     100,
            "message":      f"生成完成：{len(output_files)} 個文件（{'、'.join(f.rsplit('.', 1)[-1] for f in output_files)}）",
            "output_file":  primary,           # 兼容舊字段
            "output_files": output_files,       # 新字段：全部文件列表
            "finished_at": datetime.utcnow().isoformat(),
        })
        logger.info("[report] completed: %s", src_file.name)

    except Exception as exc:
        msg = str(exc) or repr(exc)
        logger.error("[report] FAILED task_id=%s: %s", task_id, msg, exc_info=True)
        task.update({
            "status":      "failed",
            "progress":    0,
            "message":     msg[:500],
            "finished_at": datetime.utcnow().isoformat(),
        })


# ── API ───────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    report_id:  str
    fund_id:    str
    as_of_date: str


@router.post("/generate", summary="觸發報表生成")
def generate_report(req: GenerateRequest):
    """提交生成任務（立即返回 task_id，後台線程執行腳本）。"""
    if req.report_id not in REPORT_DEFS:
        raise HTTPException(400, f"未知報表 ID：{req.report_id}")

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "task_id":     task_id,
        "report_id":   req.report_id,
        "fund_id":     req.fund_id,
        "as_of_date":  req.as_of_date,
        "status":      "queued",
        "progress":    0,
        "message":     "任務已排隊",
        "output_file": None,
        "created_at":  datetime.utcnow().isoformat(),
        "finished_at": None,
    }

    _executor.submit(_run_report_sync, task_id, req.report_id, req.fund_id, req.as_of_date)
    return _tasks[task_id]


@router.get("/result/{report_id}", summary="查詢已生成文件（頁面刷新後恢復）")
def get_existing_result(report_id: str, fund_id: str, as_of_date: str):
    """
    掃描 artefacts/reports/{report_id}/ 及 sql/mmf/output/{report_id}/，
    找與 fund_id + as_of_date 匹配的已生成文件，無需任務 ID。
    """
    if report_id not in REPORT_DEFS:
        raise HTTPException(400, f"未知報表 ID：{report_id}")

    date_str = as_of_date.replace("-", "")

    # 同一個 date 且文件名包含 date_str 的全部文件（不限 fund，用 date 作通用匹配）
    found_files: list[str] = []
    search_dirs = [REPORTS_ROOT / report_id, SQL_MMF / "output" / report_id]

    fund_name = FUND_NAMES.get(fund_id, "")

    for base_dir in search_dirs:
        if not base_dir.exists():
            continue
        for sfx, use_fund_filter in [(".xlsx", False), (".docx", True), (".pdf", True)]:
            files = sorted(
                [f for f in base_dir.iterdir()
                 if f.suffix == sfx and date_str in f.name and f.is_file()],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if use_fund_filter and fund_name:
                files = [f for f in files if f.stem.endswith(fund_name)]
            for f in files:
                if f.name not in found_files:
                    found_files.append(f.name)
        if found_files:
            break  # artefacts 優先，找到就不再查 sql/output

    return {
        "found":        bool(found_files),
        "output_files": found_files,
        "report_id":    report_id,
        "fund_id":      fund_id,
        "as_of_date":   as_of_date,
    }


@router.get("/tasks/{task_id}", summary="查詢任務進度")
def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任務不存在")
    return task


@router.get("/download/{report_id}/{filename}", summary="下載報表文件")
def download_report(report_id: str, filename: str):
    if report_id not in REPORT_DEFS:
        raise HTTPException(400, f"未知報表 ID：{report_id}")

    # 先查 artefacts/reports/，再 fallback 到 sql/mmf/output/
    for base_dir in [REPORTS_ROOT / report_id, SQL_MMF / "output" / report_id]:
        file_path = base_dir / filename
        if file_path.exists() and file_path.is_file():
            # 路徑遍歷防禦
            try:
                file_path.resolve().relative_to(base_dir.resolve())
            except ValueError:
                raise HTTPException(403, "非法路徑")

            media = {
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".pdf":  "application/pdf",
            }.get(file_path.suffix, "application/octet-stream")

            return FileResponse(path=str(file_path), filename=filename, media_type=media)

    raise HTTPException(404, f"文件不存在：{filename}")
