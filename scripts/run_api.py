#!/usr/bin/env python3
"""从 .env 读取 API_HOST / API_PORT 启动 uvicorn。

用法（在项目根目录）：
  uv run python scripts/run_api.py

派生应用按需修改：
  ENV_FILE — .env 路径（如 backend/.env）
  APP_MODULE — uvicorn 模块路径（如 policy_governance.main:app）
  subprocess.call(cmd) 的 cwd — FastAPI 代码在子目录时设为该子目录路径
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

host = os.getenv("API_HOST", "127.0.0.1")
port = os.getenv("API_PORT", "8000")
APP_MODULE = "app.main:app"

cmd = ["uv", "run", "uvicorn", APP_MODULE, "--reload", "--host", host, "--port", str(port)]
print(f"配置: {host}:{port}", file=sys.stderr)
raise SystemExit(subprocess.call(cmd))
