"""Investment Risk domain: exposure."""
from __future__ import annotations

from typing import Any

from ..domains import analyze_domain


def analyze(snapshot: Any, **kwargs: Any) -> dict[str, Any]:
    return analyze_domain("exposure", snapshot, **kwargs)
