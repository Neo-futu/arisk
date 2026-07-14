"""Run 3_skills standalone skill-agent orchestrator.

Usage:
  python 3_skills/commands/run_skill_agent.py --query "請做MMF合規核查" --skill mmf-compliance
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "3_skills" / "skills"
RUNTIME_ROOT = ROOT / "3_skills"
sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.orchestrator import SkillOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="3_skills standalone skill-agent runtime")
    parser.add_argument("--query", required=True, help="User query to route")
    parser.add_argument("--skill", required=False, help="Optional explicit skill name")
    args = parser.parse_args()

    orch = SkillOrchestrator(SKILLS_ROOT)
    result = orch.create_task(user_query=args.query, skill_name=args.skill)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
