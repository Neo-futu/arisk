"""Knowledge catalog. Retrieval stays on the existing knowledge API."""
from __future__ import annotations

from typing import Any


def catalog() -> dict[str, Any]:
    return {
        "runtime": "backend/app/api/routes/knowledge.py",
        "route": "/api/v1/knowledge",
        "target": "7_ai/knowledge",
        "calculates": False,
    }
