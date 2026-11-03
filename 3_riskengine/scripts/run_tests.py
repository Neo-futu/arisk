#!/usr/bin/env python
"""独立跑通 3_riskengine 测试（不依赖手动 cd / 额外 PYTHONPATH）。

仓库根 ``arisk/``::

    python 3_riskengine/scripts/run_tests.py
    python 3_riskengine/scripts/run_tests.py -q
    python 3_riskengine/scripts/run_tests.py tests/test_repo_structured.py

也可先做 adapters 自检::

    python 3_riskengine/scripts/run_riskengine.py --check
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "3_riskengine"
TESTS = ENGINE / "tests"


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        import pytest
    except ImportError:
        print("pytest is required: pip install pytest", file=sys.stderr)
        return 2

    # Default: full RiskEngine suite from arisk root.
    targets = [str(TESTS)] if not args or args[0].startswith("-") else []
    if targets:
        cmd = targets + args
    else:
        # Allow relative paths under 3_riskengine/
        resolved: list[str] = []
        flags: list[str] = []
        for item in args:
            if item.startswith("-"):
                flags.append(item)
                continue
            path = Path(item)
            if not path.is_absolute():
                cand = ENGINE / item
                path = cand if cand.exists() else ROOT / item
            resolved.append(str(path))
        cmd = resolved + flags

    print(f"RiskEngine tests root={ROOT}")
    return int(pytest.main(cmd))


if __name__ == "__main__":
    raise SystemExit(main())
