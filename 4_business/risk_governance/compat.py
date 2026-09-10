"""Compatibility: governance consumes 3_riskengine.limits."""
from __future__ import annotations

from importlib import import_module
from types import ModuleType


def current_limits() -> ModuleType:
    return import_module("3_riskengine.limits")
