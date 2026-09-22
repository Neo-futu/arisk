#!/usr/bin/env python
"""从仓库根运行 RiskEngine 开发入口。

    python 3_riskengine/scripts/run_riskengine.py
    python 3_riskengine/scripts/run_riskengine.py --check
    python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
for path in (SCRIPTS, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from riskengine.main import main

if __name__ == "__main__":
    raise SystemExit(main())

