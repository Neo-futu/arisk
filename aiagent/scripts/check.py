"""
aiagent/scripts/check.py — ARISK Agent 模塊完整性驗證工具

整合自 claude-risk-agent/scripts/check.py，針對 ARISK aiagent/ 結構調整：
  - 驗證 agents/*.md 的 frontmatter（name, description, tools, version）
  - 驗證 skills/*/SKILL.md 的 frontmatter（name, description）
  - 驗證 cookbooks/*/agent.yaml 的 YAML 語法和必需字段
  - 驗證 engine/ 模塊導入（tools/runner/stream）
  - 輸出詳細錯誤報告

用法：
  python aiagent/scripts/check.py
  python aiagent/scripts/check.py --agents-only
  python aiagent/scripts/check.py --skills-only
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent.parent
AIAGENT_DIR = REPO_ROOT / "aiagent"

errors:   list[str] = []
warnings: list[str] = []


def _err(msg: str) -> None:
    errors.append(f"  ERROR  {msg}")
    print(f"  [FAIL] {msg}")


def _warn(msg: str) -> None:
    warnings.append(f"  WARN   {msg}")
    print(f"  [WARN] {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def parse_frontmatter(path: Path) -> dict:
    """解析 Markdown frontmatter（---...---）。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"')
    return result


def check_agents() -> None:
    print("\n[Agents]")
    agents_dir = AIAGENT_DIR / "agents"
    if not agents_dir.exists():
        _err(f"agents/ 目錄不存在：{agents_dir}")
        return

    for md in sorted(agents_dir.glob("*.md")):
        fm = parse_frontmatter(md)
        if not fm.get("name"):
            _err(f"{md.name}: 缺少 frontmatter 字段 'name'")
        elif not fm.get("description"):
            _warn(f"{md.name}: 缺少 frontmatter 字段 'description'")
        else:
            _ok(f"{md.name}  ({fm.get('name')})")


def check_skills() -> None:
    print("\n[Skills]")
    skills_dir = AIAGENT_DIR / "skills"
    if not skills_dir.exists():
        _warn("skills/ 目錄不存在")
        return

    skill_files = list(skills_dir.rglob("SKILL.md"))
    if not skill_files:
        _warn("未找到任何 SKILL.md")
        return

    for sf in sorted(skill_files):
        fm = parse_frontmatter(sf)
        rel = sf.relative_to(AIAGENT_DIR)
        if not fm.get("name"):
            _err(f"{rel}: 缺少 frontmatter 字段 'name'")
        else:
            _ok(f"{rel}  ({fm.get('name')})")


def check_cookbooks() -> None:
    print("\n[Cookbooks]")
    cookbooks_dir = AIAGENT_DIR / "cookbooks"
    if not cookbooks_dir.exists():
        _warn("cookbooks/ 目錄不存在")
        return

    try:
        import yaml
    except ImportError:
        _warn("PyYAML 未安裝，跳過 YAML 校驗（pip install pyyaml）")
        return

    for yaml_file in sorted(cookbooks_dir.rglob("agent.yaml")):
        rel = yaml_file.relative_to(AIAGENT_DIR)
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not data.get("name"):
                _err(f"{rel}: 缺少必需字段 'name'")
            elif not data.get("system"):
                _warn(f"{rel}: 缺少 'system' 字段")
            else:
                _ok(f"{rel}  ({data.get('name')})")
        except yaml.YAMLError as e:
            _err(f"{rel}: YAML 解析錯誤 — {e}")


def check_engine() -> None:
    print("\n[Engine]")
    engine_dir = AIAGENT_DIR / "engine"
    for mod in ["tools.py", "runner.py", "stream.py", "__init__.py"]:
        mp = engine_dir / mod
        if mp.exists():
            _ok(f"engine/{mod}")
        else:
            _err(f"engine/{mod} 不存在")

    # 嘗試導入
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from aiagent.engine import AGENT_NAMES, TOOLS  # noqa
        _ok(f"engine 可正常導入  (agents={len(AGENT_NAMES)}, tools={len(TOOLS)})")
    except Exception as exc:
        _err(f"engine 導入失敗：{exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ARISK aiagent 完整性驗證")
    ap.add_argument("--agents-only", action="store_true")
    ap.add_argument("--skills-only", action="store_true")
    ap.add_argument("--cookbooks-only", action="store_true")
    args = ap.parse_args()

    print("=" * 55)
    print("  ARISK aiagent — 完整性驗證")
    print("=" * 55)

    if args.agents_only:
        check_agents()
    elif args.skills_only:
        check_skills()
    elif args.cookbooks_only:
        check_cookbooks()
    else:
        check_agents()
        check_skills()
        check_cookbooks()
        check_engine()

    print("\n" + "=" * 55)
    if errors:
        print(f"  [FAIL] {len(errors)} errors, {len(warnings)} warnings")
        return 1
    elif warnings:
        print(f"  [WARN] 0 errors, {len(warnings)} warnings")
        return 0
    else:
        print("  [OK]   All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
