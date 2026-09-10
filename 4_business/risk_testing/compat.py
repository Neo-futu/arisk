"""Compatibility entry for risk_testing use cases.

Current engine remains in 2_processing.tools.risk_testing.
This module does not copy algorithms; it resolves the live implementation.
"""
from __future__ import annotations

from importlib import import_module
from types import ModuleType


def current_engine() -> ModuleType:
    return import_module("2_processing.tools.risk_testing")
