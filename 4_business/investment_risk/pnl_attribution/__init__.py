"""Investment Risk domain: pnl_attribution — 业绩归因（Brinson / Campisi）。"""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """KPI 包 + RiskEngine 业绩归因七大业务模块。"""

    return analyze_domain("pnl_attribution", snapshot, **kwargs)


def fundamentals(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """仅归因业务模块（与 indicators 业绩归因 Tab 对齐）。"""

    from importlib import import_module

    return import_module("3_riskengine").RiskEngine().bind(snapshot).pnl().attribution(**kwargs)
