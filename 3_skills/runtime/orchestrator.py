"""3_skills standalone orchestration runtime.

No aiagent dependency. This is a dedicated Skill Agent runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .skill_registry import SkillRegistry, SkillSpec


@dataclass
class SkillTask:
    task_id: str
    status: str
    skill_name: str
    created_at: str


class SkillOrchestrator:
    """Route user query to a skill and return an execution plan payload."""

    def __init__(self, skills_root: Path) -> None:
        self.registry = SkillRegistry(skills_root)
        self.registry.refresh()

    def refresh(self) -> int:
        return self.registry.refresh()

    def route(self, user_query: str, skill_name: str | None = None) -> SkillSpec | None:
        if skill_name:
            return self.registry.get(skill_name)
        return self.registry.route(user_query)

    def create_task(self, user_query: str, skill_name: str | None = None) -> dict:
        spec = self.route(user_query, skill_name)
        if not spec:
            return {
                "error": "no_skill_matched",
                "available_skills": self.registry.list_skills(),
                "message": "未匹配到技能，請指定 skill_name 或調整問題描述",
            }

        task = SkillTask(
            task_id=f"skill-{int(datetime.now().timestamp() * 1000)}",
            status="planned",
            skill_name=spec.name,
            created_at=datetime.now().isoformat(),
        )
        return {
            "task": task.__dict__,
            "agent": "3-skills-agent",
            "skill": {
                "name": spec.name,
                "description": spec.description,
                "path": str(spec.path),
                "triggers": spec.triggers,
            },
            "execution_plan": _extract_steps(spec.content),
            "raw_skill_content": spec.content,
        }


def _extract_steps(content: str) -> list[str]:
    lines = [ln.strip() for ln in content.splitlines()]
    steps: list[str] = []
    in_steps = False
    for line in lines:
        if line.startswith("##") and ("執行步驟" in line or "核查流程" in line):
            in_steps = True
            continue
        if in_steps and line.startswith("##"):
            break
        if in_steps and line and (line.startswith("Step") or line.startswith("### Step") or line.startswith("-") or line.startswith("*") or line.startswith("1.") or line.startswith("2.") or line.startswith("3.")):
            steps.append(line)

    if steps:
        return steps

    # Fallback: collect top-level Step headings from entire document.
    for line in lines:
        if line.startswith("### Step") or re.match(r"^Step\s+\d+", line):
            steps.append(line)
    return steps
