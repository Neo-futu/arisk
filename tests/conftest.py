"""让测试无需安装即可 import app/handler.py。

把仓库根的 app/ 加入 sys.path，并固定 APP_NAME/ENV 环境变量以获得确定输出。
"""

import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))


@pytest.fixture(autouse=True)
def _fixed_env(monkeypatch):
    monkeypatch.setenv("APP_NAME", "demo-app")
    monkeypatch.setenv("ENV", "dev")
