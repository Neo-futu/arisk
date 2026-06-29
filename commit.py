"""
commit.py  一鍵 git add / commit / push
用法：
    python commit.py "你的 commit message"
    python commit.py "fix: 修復 17_stress_test.sql 浮息債久期計算"
"""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print('Usage: python commit.py "commit message"')
        sys.exit(1)

    message = sys.argv[1]

    steps = [
        (["git", "add", "."],               "Stage all"),
        (["git", "commit", "-m", message],  "Commit"),
        (["git", "push", "origin", "main"], "Push"),
    ]

    for cmd, label in steps:
        print(f"\n-- {label} --")
        code = run(cmd)
        if code != 0:
            print(f"\nFailed at: {label} (exit {code})")
            sys.exit(code)

    print("\nDone.")


if __name__ == "__main__":
    main()
