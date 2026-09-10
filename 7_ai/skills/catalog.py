"""Skill catalog. Files stay in 3_skills/; this layer only indexes names."""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def catalog() -> dict[str, Any]:
    skills_root = ROOT / "3_skills" / "skills"
    names: list[str] = []
    if skills_root.is_dir():
        names = sorted(path.parent.name for path in skills_root.glob("*/SKILL.md"))
    return {
        "runtime": "3_skills/",
        "target": "7_ai/skills",
        "skills": names,
        "calculates": False,
    }
