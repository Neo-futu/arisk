"""Investment Risk domain: exposure — 整体风险敞口 / 基本信息。"""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """KPI 包 + RiskEngine 组合/币种/成立日/WAM·WAL/投管人员。"""

    return analyze_domain("exposure", snapshot, **kwargs)


def fundamentals(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """基本信息业务模块。"""

    from importlib import import_module

    return import_module("3_riskengine").RiskEngine().bind(snapshot).portfolio().basic_info(**kwargs)


def risk_indicators(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    """风险指标 Tab：核心五卡 / 滚动波动 / VaR 三方法 / 六大风控类型。"""

    from importlib import import_module

    return (
        import_module("3_riskengine")
        .RiskEngine()
        .bind(snapshot)
        .portfolio()
        .risk_indicators(**kwargs)
    )
