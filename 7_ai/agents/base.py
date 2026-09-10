"""Shared agent spec. Agents declare tools; they do not calculate."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    title: str
    tools: tuple[str, ...]
    default_intent: str
    min_role: str = "viewer"
