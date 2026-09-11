"""2_processing.compatibility — facades from legacy tools to new layers."""

from .legacy_tools import LEGACY_MODULES, TARGET_ALIASES, load, load_target

__all__ = ["LEGACY_MODULES", "TARGET_ALIASES", "load", "load_target"]
