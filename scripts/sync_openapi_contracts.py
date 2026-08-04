"""Sync OpenAPI contracts into frontend/openapi for code generation.

Usage:
  python scripts/sync_openapi_contracts.py

Environment overrides:
  BACKEND_OPENAPI_URL
  PROCESSING_OPENAPI_URL
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.request
from urllib.error import URLError

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND_OPENAPI_DIR = ROOT / "frontend" / "openapi"

BACKEND_OPENAPI_URL = os.getenv("BACKEND_OPENAPI_URL", "http://localhost:8000/openapi.json")
PROCESSING_OPENAPI_URL = os.getenv("PROCESSING_OPENAPI_URL", "http://localhost:8001/openapi.json")


def fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # nosec B310 - local dev URLs only
            payload = response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"Cannot fetch OpenAPI from {url}: {exc}") from exc

    data = json.loads(payload)
    if not isinstance(data, dict) or "openapi" not in data:
        raise ValueError(f"Invalid OpenAPI payload from {url}")
    return data


def write_contract(data: dict, output_path: pathlib.Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync OpenAPI contracts for frontend code generation")
    parser.add_argument("--backend-url", default=BACKEND_OPENAPI_URL)
    parser.add_argument("--processing-url", default=PROCESSING_OPENAPI_URL)
    parser.add_argument("--skip-backend", action="store_true")
    parser.add_argument("--skip-processing", action="store_true")
    args = parser.parse_args()

    if args.skip_backend and args.skip_processing:
        raise SystemExit("Nothing to sync: both --skip-backend and --skip-processing are set")

    synced: list[str] = []

    if not args.skip_backend:
        backend_data = fetch_json(args.backend_url)
        write_contract(backend_data, FRONTEND_OPENAPI_DIR / "backend.json")
        synced.append(f"- backend    -> {FRONTEND_OPENAPI_DIR / 'backend.json'}")

    if not args.skip_processing:
        processing_data = fetch_json(args.processing_url)
        write_contract(processing_data, FRONTEND_OPENAPI_DIR / "processing.json")
        synced.append(f"- processing -> {FRONTEND_OPENAPI_DIR / 'processing.json'}")

    print("Synced OpenAPI contracts:")
    for line in synced:
        print(line)


if __name__ == "__main__":
    main()
