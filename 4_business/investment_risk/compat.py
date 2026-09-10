"""Compatibility entry for investment risk use cases.

Current analysis remains in 2_processing.tools.performance.investment_analysis.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType


def current_analysis() -> ModuleType:
    return import_module("2_processing.tools.performance.investment_analysis")
