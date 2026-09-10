"""Vendor import isolation. Only adapter packages import third-party libraries."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class VendorProbe:
    """Result of probing a third-party library without leaking its types."""

    name: str
    available: bool
    version: str | None
    module_path: str | None
    error: str | None = None


def probe_module(name: str, version_attr: str = "__version__") -> tuple[VendorProbe, ModuleType | None]:
    """Import a vendor module if present; never raise to callers."""

    try:
        module = import_module(name)
    except Exception as exc:  # noqa: BLE001 — adapter must initialize even when vendor is absent
        return VendorProbe(name, False, None, None, f"{type(exc).__name__}: {exc}"), None
    version = getattr(module, version_attr, None)
    if version is not None:
        version = str(version)
    path = getattr(module, "__file__", None)
    return VendorProbe(name, True, version, str(path) if path else None, None), module


def optional_attr(module: ModuleType | None, attribute: str, default: Any = None) -> Any:
    """Read a vendor attribute without exposing missing-module errors."""

    if module is None:
        return default
    return getattr(module, attribute, default)
