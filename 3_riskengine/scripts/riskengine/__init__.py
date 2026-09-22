"""开发用 RiskEngine 包。

- ``config``  — 引入、参数、夹具 / DB 组合加载
- ``objects`` — Engine / BoundEngine / SliceSpec
- ``main``    — BoundEngine 示例运行入口

用法（仓库根 ``arisk/``）::

    python -m riskengine
    python -m riskengine --check
    python -m riskengine --fund-id BHMMF001 --as-of-date 2026-09-01
"""
from __future__ import annotations

from .config import (
    BOOKS,
    CANONICAL_TABLES,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MARKET_FALLBACK,
    DEFAULT_MARKET_FALLBACK_SOURCE,
    DEFAULT_MARKET_LOOKBACK_DAYS,
    DEFAULT_MARKET_SOURCE,
    EQUITY_OFF,
    RISKENGINE_NAME,
    RISKENGINE_VERSION,
    SCENARIOS,
    Shock,
    ShockMode,
    RiskFactorType,
    build_database_url,
    list_live_portfolios,
    load_book,
    load_snapshot,
    load_snapshot_sync,
    shock_credit,
    shock_equity,
    shock_fx,
    shock_rate,
    shock_vol,
)
from .objects import (
    DEFAULT_SLICE,
    BoundEngine,
    Engine,
    SliceSpec,
    bind,
    verify_slice,
)

__all__ = [
    "BOOKS",
    "CANONICAL_TABLES",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_MARKET_FALLBACK",
    "DEFAULT_MARKET_FALLBACK_SOURCE",
    "DEFAULT_MARKET_LOOKBACK_DAYS",
    "DEFAULT_MARKET_SOURCE",
    "DEFAULT_SLICE",
    "EQUITY_OFF",
    "BoundEngine",
    "Engine",
    "RISKENGINE_NAME",
    "RISKENGINE_VERSION",
    "RiskFactorType",
    "SCENARIOS",
    "Shock",
    "ShockMode",
    "SliceSpec",
    "bind",
    "build_database_url",
    "list_live_portfolios",
    "load_book",
    "load_snapshot",
    "load_snapshot_sync",
    "shock_credit",
    "shock_equity",
    "shock_fx",
    "shock_rate",
    "shock_vol",
    "verify_slice",
]
