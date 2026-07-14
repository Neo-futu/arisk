"""3_skills registry loader for SKILL.md files.

This module is intentionally independent from aiagent.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path


@dataclass
class SkillSpec:
    name: str
    path: Path
    description: str
    triggers: list[str]
    content: str


class SkillRegistry:
    """Load and search skill specs from 3_skills/skills."""

    def __init__(self, skills_root: Path) -> None:
        self.skills_root = skills_root
        self._skills: dict[str, SkillSpec] = {}

    def refresh(self) -> int:
        self._skills.clear()
        for md_path in self.skills_root.glob("*/SKILL.md"):
            spec = self._parse_skill(md_path)
            if spec:
                self._skills[spec.name] = spec
        return len(self._skills)

    def list_skills(self) -> list[str]:
        return sorted(self._skills)

    def get(self, name: str) -> SkillSpec | None:
        return self._skills.get(name)

    def route(self, user_query: str) -> SkillSpec | None:
        q = user_query.lower()
        for spec in self._skills.values():
            if spec.name.lower() in q:
                return spec
            if any(t.lower() in q for t in spec.triggers):
                return spec
        return None

    def _parse_skill(self, md_path: Path) -> SkillSpec | None:
        text = md_path.read_text(encoding="utf-8")
        frontmatter, content = _split_frontmatter(text)
        name = frontmatter.get("name") or md_path.parent.name
        description = frontmatter.get("description", "")
        triggers = _parse_list(frontmatter.get("triggers", ""))
        return SkillSpec(
            name=name,
            path=md_path,
            description=description,
            triggers=triggers,
            content=content.strip(),
        )


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    fm: dict[str, str] = {}
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, flags=re.DOTALL)
    if not m:
        return fm, text
    raw, body = m.group(1), m.group(2)
    current_list_key: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if current_list_key and stripped.startswith("-"):
            old = fm.get(current_list_key, "")
            item = stripped[1:].strip()
            fm[current_list_key] = f"{old},{item}" if old else item
            continue
        if not stripped.startswith("-"):
            current_list_key = None
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        value = v.strip()
        fm[key] = value
        if value == "":
            current_list_key = key
    return fm, body


def _parse_list(value: str) -> list[str]:
    if not value:
        return []
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = json.loads(stripped.replace("'", '"'))
            if isinstance(parsed, list):
                return [str(i).strip() for i in parsed if str(i).strip()]
        except Exception:
            pass
    if stripped.startswith("[") and stripped.endswith("]"):
        items = stripped[1:-1].split(",")
        return [i.strip().strip("\"'") for i in items if i.strip()]
    if "," in stripped:
        return [i.strip().strip("\"'") for i in stripped.split(",") if i.strip()]
    return [stripped]
