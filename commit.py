"""
commit.py  —  一鍵 git add / commit / push
用法：
    python commit.py "你的 commit message"
    python commit.py "fix: 修復 17_stress_test.sql 浮息債久期計算"
"""
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=__file__[:__file__.rfind("\\")])
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print("用法：python commit.py \"commit message\"")
        sys.exit(1)

    message = sys.argv[1]

    steps = [
        (["git", "add", "."],                          "Stage all changes"),
        (["git", "commit", "-m", message],             "Commit"),
        (["git", "push", "origin", "main"],            "Push to remote"),
    ]

    for cmd, label in steps:
        print(f"\n── {label} ──")
        code = run(cmd)
        if code != 0:
            print(f"\n❌ 失敗於：{label}（exit code {code}）")
            sys.exit(code)

    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
