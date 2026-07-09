"""
aiagent/scripts/sync_skills.py — 從 claude-risk-agent 同步技能到 ARISK

整合自 claude-risk-agent/scripts/sync-agent-skills.py。
claude-risk-agent 的 vertical-plugins/*/skills/* 是 Skill 的唯一真實來源，
本腳本將選定的技能同步到 aiagent/skills/。

同步規則：
  - 只同步與 ARISK MMF 業務相關的技能
  - 目標文件已存在時，詢問是否覆蓋（--force 跳過確認）

用法：
  python aiagent/scripts/sync_skills.py
  python aiagent/scripts/sync_skills.py --force
  python aiagent/scripts/sync_skills.py --list
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT    = Path(__file__).parent.parent.parent
AIAGENT_DIR  = REPO_ROOT / "aiagent"
RISK_AGENT   = Path(r"D:\vsproject\claude-risk-agent")

# 要同步的技能：(源相對路徑, 目標相對路徑)
SYNC_MAP = [
    # fund-admin skills
    ("plugins/vertical-plugins/fund-admin/skills/gl-recon",            "skills/fund-admin/gl-recon"),
    ("plugins/vertical-plugins/fund-admin/skills/nav-tieout",          "skills/fund-admin/nav-tieout"),
    ("plugins/vertical-plugins/fund-admin/skills/variance-commentary",  "skills/fund-admin/variance-commentary"),
    ("plugins/vertical-plugins/fund-admin/skills/roll-forward",        "skills/fund-admin/roll-forward"),
    ("plugins/vertical-plugins/fund-admin/skills/break-trace",         "skills/fund-admin/break-trace"),
    ("plugins/vertical-plugins/fund-admin/skills/accrual-schedule",    "skills/fund-admin/accrual-schedule"),
    # operations skills (KYC)
    ("plugins/vertical-plugins/operations/skills/kyc-doc-parse",       "skills/operations/kyc-doc-parse"),
    ("plugins/vertical-plugins/operations/skills/kyc-rules",           "skills/operations/kyc-rules"),
    # financial-analysis skills
    ("plugins/vertical-plugins/financial-analysis/skills/audit-xls",   "skills/financial-analysis/audit-xls"),
    # equity-research skills (sector analysis)
    ("plugins/vertical-plugins/equity-research/skills/sector-overview", "skills/sector-overview/_upstream"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="同步 claude-risk-agent 技能到 ARISK")
    ap.add_argument("--force", action="store_true", help="覆蓋已存在的文件")
    ap.add_argument("--list",  action="store_true", help="只列出同步清單，不執行")
    args = ap.parse_args()

    if not RISK_AGENT.exists():
        print(f"⚠ claude-risk-agent 不存在：{RISK_AGENT}")
        print("  請確認路徑後重試")
        sys.exit(1)

    print(f"源：{RISK_AGENT}")
    print(f"目標：{AIAGENT_DIR}")
    print()

    synced = skipped = missing = 0

    for src_rel, dst_rel in SYNC_MAP:
        src = RISK_AGENT / src_rel
        dst = AIAGENT_DIR / dst_rel

        skill_file = src / "SKILL.md"
        if not skill_file.exists():
            print(f"  ⚠ 源不存在：{src_rel}/SKILL.md")
            missing += 1
            continue

        if args.list:
            status = "已存在" if (dst / "SKILL.md").exists() else "新增"
            print(f"  [{status:4s}] {src_rel} → {dst_rel}")
            continue

        dst.mkdir(parents=True, exist_ok=True)
        target = dst / "SKILL.md"

        if target.exists() and not args.force:
            print(f"  · 跳過（已存在）：{dst_rel}/SKILL.md  （用 --force 覆蓋）")
            skipped += 1
            continue

        shutil.copy2(skill_file, target)
        print(f"  ✓ 同步：{dst_rel}/SKILL.md")
        synced += 1

    if not args.list:
        print(f"\n完成：同步 {synced}，跳過 {skipped}，源缺失 {missing}")


if __name__ == "__main__":
    main()
