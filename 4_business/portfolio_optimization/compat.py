"""Compatibility entry for portfolio optimization use cases.

Current optimizer remains in 2_processing.tools.performance.portfolio_optimizer.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType


def current_optimizer() -> ModuleType:
    return import_module("2_processing.tools.performance.portfolio_optimizer")
