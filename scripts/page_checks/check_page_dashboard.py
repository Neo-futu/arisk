from pathlib import Path

from core import run_named_page


if __name__ == "__main__":
    page_key = Path(__file__).stem.replace("check_page_", "", 1)
    raise SystemExit(run_named_page(page_key))