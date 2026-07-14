"""
scripts/dev.py — FSI 本地整合開發啟動器

目標：提供類似 full-stack-fastapi-template 的統一本地啟動入口，
但同時覆蓋 FSI 的分層能力服務。

預設 profile：
    web       processing + 6_entry + backend + frontend
    agent     processing + 6_entry
    full      web + mcp-gateway + internal-mcp + wind-mcp

典型用法：
    python scripts/dev.py
    python scripts/dev.py --profile agent
    python scripts/dev.py --with-mcp
    python scripts/dev.py --with-internal-mcp
    python scripts/dev.py --only backend
    python scripts/dev.py --parts processing backend frontend
    python scripts/dev.py --list-parts
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── ANSI 顏色（Windows 需開啟 ANSI 支持） ─────────────────────────
COLORS = {
    "processing": "\033[36m",   # 青
    "entry":      "\033[34m",   # 藍
    "backend":    "\033[32m",   # 綠
    "frontend":   "\033[35m",   # 紫
    "mcp-gateway": "\033[92m",  # 亮綠
    "internal-mcp": "\033[96m", # 亮青
    "wind-mcp":   "\033[95m",   # 亮紫
    "reset":      "\033[0m",
    "bold":       "\033[1m",
    "red":        "\033[31m",
    "yellow":     "\033[33m",
}

DEFAULTS = {
    "DATABASE_URL": "postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk",
    "PROCESSING_API_KEY": "internal_key_change_me",
    "PROCESSING_API_URL": "http://localhost:8001",
    "ENTRY_API_URL": "http://localhost:8010",
    "REDIS_URL": "redis://localhost:6379/0",
}

PROFILES = {
    "web": ["processing", "entry", "backend", "frontend"],
    "agent": ["processing", "entry"],
    "full": ["processing", "entry", "backend", "frontend", "mcp-gateway", "internal-mcp", "wind-mcp"],
}


def _frontend_cmd() -> list[str]:
    if shutil.which("bun"):
        return ["bun", "dev"]
    if sys.platform == "win32":
        return ["npm.cmd", "run", "dev"]
    return ["npm", "run", "dev"]


def build_processes() -> dict[str, dict]:
    return {
        "processing": {
            "cmd": [
                sys.executable, "-m", "uvicorn",
                "2_processing.api.main:app",
                "--host", "0.0.0.0",
                "--port", "8001",
                "--reload",
            ],
            "cwd": ROOT,
            "env_extra": {"PYTHONPATH": str(ROOT)},
            "env_defaults": {
                "DATABASE_URL": DEFAULTS["DATABASE_URL"],
                "PROCESSING_API_KEY": DEFAULTS["PROCESSING_API_KEY"],
                "REDIS_URL": DEFAULTS["REDIS_URL"],
            },
            "ready_msg": "Application startup complete",
            "url": "http://localhost:8001/docs",
            "kind": "service",
        },
        "entry": {
            "cmd": [
                sys.executable, "-m", "uvicorn",
                "6_entry.web.app:app",
                "--host", "0.0.0.0",
                "--port", "8010",
                "--reload",
            ],
            "cwd": ROOT,
            "env_extra": {"PYTHONPATH": str(ROOT)},
            "env_defaults": {
                "PROCESSING_API_URL": DEFAULTS["PROCESSING_API_URL"],
                "PROCESSING_API_KEY": DEFAULTS["PROCESSING_API_KEY"],
            },
            "ready_msg": "Application startup complete",
            "url": "http://localhost:8010/docs",
            "kind": "service",
        },
        "backend": {
            "cmd": [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--reload",
            ],
            "cwd": ROOT / "backend",
            "env_extra": {},
            "env_defaults": {
                "ENTRY_API_URL": DEFAULTS["ENTRY_API_URL"],
                "PROCESSING_API_URL": DEFAULTS["PROCESSING_API_URL"],
                "PROCESSING_API_KEY": DEFAULTS["PROCESSING_API_KEY"],
            },
            "ready_msg": "Application startup complete",
            "url": "http://localhost:8000/docs",
            "kind": "service",
        },
        "frontend": {
            "cmd": _frontend_cmd(),
            "cwd": ROOT / "frontend",
            "env_extra": {},
            "env_defaults": {},
            "ready_msg": "ready in",
            "url": "http://localhost:5173",
            "kind": "service",
        },
        "mcp-gateway": {
            "cmd": [sys.executable, "-m", "4_mcp.gateway.mcp_gateway"],
            "cwd": ROOT,
            "env_extra": {"PYTHONPATH": str(ROOT)},
            "env_defaults": {
                "MCP_GATEWAY_PORT": "8002",
                "MCP_GATEWAY_URL": "http://127.0.0.1:8002",
            },
            "ready_msg": "Uvicorn running on",
            "url": "http://localhost:8002/health",
            "kind": "service",
        },
        "internal-mcp": {
            "cmd": [sys.executable, str(ROOT / "4_mcp" / "internal" / "internal_mcp_server.py")],
            "cwd": ROOT,
            "env_extra": {"PYTHONPATH": str(ROOT)},
            "env_defaults": {"DATABASE_URL": DEFAULTS["DATABASE_URL"]},
            "ready_msg": None,
            "url": "stdio MCP server (client activated)",
            "kind": "tool",
        },
        "wind-mcp": {
            "cmd": [sys.executable, str(ROOT / "4_mcp" / "wind" / "wind_mcp_server.py")],
            "cwd": ROOT,
            "env_extra": {"PYTHONPATH": str(ROOT)},
            "env_defaults": {},
            "ready_msg": None,
            "url": "stdio MCP server (client activated)",
            "kind": "tool",
        },
    }


PROCESSES = build_processes()


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _print(name: str, line: str) -> None:
    color = COLORS.get(name, "")
    reset = COLORS["reset"]
    prefix = f"{color}[{name:12s}]{reset}"
    print(f"{prefix} {line}", flush=True)


def _stream(proc: subprocess.Popen, name: str, ready_event: threading.Event) -> None:
    """串流進程輸出，偵測啟動就緒信號。"""
    assert proc.stdout
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", errors="replace").rstrip()
        _print(name, line)
        ready_msg = PROCESSES[name]["ready_msg"]
        if ready_msg and not ready_event.is_set() and ready_msg in line:
            ready_event.set()
    # 進程退出
    rc = proc.wait()
    if rc != 0:
        _print(name, f"{COLORS['red']}進程退出，返回碼 {rc}{COLORS['reset']}")


def start_process(name: str) -> tuple[subprocess.Popen, threading.Event]:
    cfg = PROCESSES[name]
    env = os.environ.copy()
    env.update(cfg.get("env_defaults", {}))
    env.update(cfg["env_extra"])

    proc = subprocess.Popen(
        cfg["cmd"],
        cwd=cfg["cwd"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    ready = threading.Event()
    if not cfg["ready_msg"]:
        ready.set()
    t = threading.Thread(target=_stream, args=(proc, name, ready), daemon=True)
    t.start()
    _print(name, f"已啟動（PID {proc.pid}）→ {cfg['url']}")
    return proc, ready


def parse_args():
    p = argparse.ArgumentParser(description="FSI 本地開發一鍵啟動")
    p.add_argument(
        "--profile",
        choices=list(PROFILES),
        default="web",
        help="啟動預設組合：web / agent / full",
    )
    p.add_argument("--no-frontend", action="store_true", help="不啟動前端")
    p.add_argument("--no-backend", action="store_true", help="不啟動 backend")
    p.add_argument("--no-entry", action="store_true", help="不啟動 6_entry")
    p.add_argument("--no-processing", action="store_true", help="不啟動 processing")
    p.add_argument("--with-mcp", action="store_true", help="附帶啟動 MCP 全套（gateway + internal + wind）")
    p.add_argument("--with-mcp-gateway", action="store_true", help="附帶啟動 MCP Gateway（8002）")
    p.add_argument("--with-internal-mcp", action="store_true", help="附帶啟動 internal MCP")
    p.add_argument("--with-wind-mcp", action="store_true", help="附帶啟動 Wind MCP")
    p.add_argument(
        "--only",
        choices=list(PROCESSES),
        help="只啟動指定進程",
    )
    p.add_argument(
        "--parts",
        nargs="+",
        choices=list(PROCESSES),
        help="顯式指定要啟動的多個部分，覆蓋 profile",
    )
    p.add_argument("--list-parts", action="store_true", help="列出可啟動部分後退出")
    p.add_argument("--dry-run", action="store_true", help="僅打印啟動計劃，不實際啟動")
    return p.parse_args()


def main() -> None:
    # Windows 開啟 ANSI 支持
    if sys.platform == "win32":
        os.system("")

    args = parse_args()

    if args.list_parts:
        print("可啟動部分：")
        for name in PROCESSES:
            cfg = PROCESSES[name]
            print(f"- {name:12s} [{cfg['kind']}] -> {cfg['url']}")
        print("\nProfile：")
        for profile, parts in PROFILES.items():
            print(f"- {profile:8s}: {', '.join(parts)}")
        return

    targets: list[str]
    if args.only:
        targets = [args.only]
    elif args.parts:
        targets = _unique_preserve_order(list(args.parts))
    else:
        targets = list(PROFILES[args.profile])
        if args.no_frontend and "frontend" in targets:
            targets.remove("frontend")
        if args.no_backend and "backend" in targets:
            targets.remove("backend")
        if args.no_entry and "entry" in targets:
            targets.remove("entry")
        if args.no_processing and "processing" in targets:
            targets.remove("processing")
        if args.with_mcp or args.with_mcp_gateway:
            if "mcp-gateway" not in targets:
                targets.append("mcp-gateway")
        if args.with_mcp:
            if "internal-mcp" not in targets:
                targets.append("internal-mcp")
            if "wind-mcp" not in targets:
                targets.append("wind-mcp")
        if args.with_internal_mcp and "internal-mcp" not in targets:
            targets.append("internal-mcp")
        if args.with_wind_mcp and "wind-mcp" not in targets:
            targets.append("wind-mcp")

    targets = _unique_preserve_order(targets)

    bold, reset = COLORS["bold"], COLORS["reset"]
    print(f"\n{bold}ARISK — 本地開發啟動{reset}")
    print(f"Profile：{args.profile}")
    print(f"啟動進程：{', '.join(targets)}")
    print("說明：3_skills 是資產層（SKILL / prompt / commands），不是常駐進程。\n")

    if args.dry_run:
        print("Dry-run 啟動計劃：")
        for name in targets:
            cfg = PROCESSES[name]
            cmd = " ".join(cfg["cmd"])
            print(f"- {name:12s} cwd={cfg['cwd']} cmd={cmd}")
        return

    procs: list[subprocess.Popen] = []
    events: list[threading.Event] = []

    for name in targets:
        proc, ready = start_process(name)
        procs.append(proc)
        events.append(ready)

    # 等待所有進程就緒（最多 30s）
    print(f"\n等待所有進程就緒...")
    deadline = time.time() + 30
    for name, ev in zip(targets, events):
        remaining = max(0, deadline - time.time())
        if ev.wait(timeout=remaining):
            _print(name, f"{COLORS['yellow']}✓ 就緒{reset}")
        else:
            _print(name, f"{COLORS['red']}⚠ 啟動超時（進程可能仍在運行）{reset}")

    print(f"\n{bold}全部進程已啟動：{reset}")
    for name in targets:
        cfg = PROCESSES[name]
        print(f"  {COLORS.get(name, '')}●{reset} {name:12s}  {cfg['url']}  [{cfg['kind']}]")

    print("\n端口約定：")
    print("  frontend   : 5173")
    print("  backend    : 8000")
    print("  6_entry    : 8010")
    print("  processing : 8001")
    if "mcp-gateway" in targets:
        print("  mcp-gateway: 8002")

    print(f"\n按 Ctrl+C 停止所有進程\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print(f"\n{COLORS['yellow']}正在停止所有進程...{reset}")
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("已停止。")


if __name__ == "__main__":
    main()
