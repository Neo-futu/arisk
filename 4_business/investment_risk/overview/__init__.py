"""Investment Risk domain: overview — 组合概况业务模块。"""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """KPI 包 + RiskEngine 组合/区间收益/配置/Top10/行业。"""

    return analyze_domain("overview", snapshot, **kwargs)


def fundamentals(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """仅业务模块（与 ``/investment-risk/overview`` 对齐）。"""

    from importlib import import_module

    return import_module("3_riskengine").RiskEngine().bind(snapshot).portfolio().overview(**kwargs)
