import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="svc-a database migration placeholder")
    parser.add_argument("--check", action="store_true", help="Exit 0 when no pending migration exists")
    parser.add_argument("command", nargs="?", default="run", choices=["run"])
    args = parser.parse_args()

    if args.check:
        print("No pending migrations in template placeholder.")
        return 0

    print("No-op migration placeholder. Replace this script with real migration logic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
