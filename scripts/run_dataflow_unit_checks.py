"""Layer-by-layer dataflow unit checks for ARISK.

Covers:
- DB reachability (and optional SQL probe)
- processing health and protected risk endpoints
- backend health, auth, and proxied risk endpoints
- MCP gateway port listening
- frontend home availability

Usage examples:
  python scripts/run_dataflow_unit_checks.py
  python scripts/run_dataflow_unit_checks.py --only processing_health backend_login
  python scripts/run_dataflow_unit_checks.py --fund-id BHMMF001 --as-of-date 2026-08-01
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


@dataclass
class CheckResult:
    name: str
    layer: str
    ok: bool
    message: str
    detail: str = ""


def load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        data[key] = value
    return data


def get_env(key: str, default: str, file_env: dict[str, str]) -> str:
    return os.getenv(key) or file_env.get(key) or default


def http_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json_body: dict | None = None,
    form_body: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict | list | str]:
    if params:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"

    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    body_bytes = None
    if json_body is not None:
        req_headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(json_body).encode("utf-8")
    elif form_body is not None:
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        body_bytes = urllib.parse.urlencode(form_body).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, headers=req_headers, data=body_bytes)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def http_text(url: str, timeout: float = 20.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers={"Accept": "text/html,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def check_tcp(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True, f"connected to {host}:{port}"
    except OSError as exc:
        return False, f"cannot connect {host}:{port} ({exc})"
    finally:
        sock.close()


def last_trade_date_text() -> str:
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ARISK layer-by-layer unit checks")
    parser.add_argument("--fund-id", default="BHMMF001")
    parser.add_argument("--as-of-date", default=last_trade_date_text())
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    file_env = load_env_file(ENV_PATH)

    backend_base = get_env("BACKEND_PUBLIC_URL", "http://localhost:8000", file_env).rstrip("/")
    processing_base = get_env("PROCESSING_API_URL", "http://localhost:8001", file_env).rstrip("/")
    frontend_base = get_env("FRONTEND_HOST", "http://localhost:5173", file_env).rstrip("/")
    processing_key = get_env("PROCESSING_API_KEY", "internal_key_change_me", file_env)
    admin_email = get_env("FIRST_SUPERUSER", "admin@fsi.com", file_env)
    admin_password = get_env("FIRST_SUPERUSER_PASSWORD", "changethis", file_env)

    postgres_host = get_env("POSTGRES_SERVER", get_env("POSTGRES_HOST", "localhost", file_env), file_env)
    postgres_port = int(get_env("POSTGRES_PORT", "5432", file_env))
    mcp_gateway_port = int(get_env("MCP_GATEWAY_PORT", "8002", file_env))

    token_holder: dict[str, str] = {}

    def wrap(name: str, layer: str, fn: Callable[[], CheckResult]) -> Callable[[], CheckResult]:
        def runner() -> CheckResult:
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                return CheckResult(name=name, layer=layer, ok=False, message=f"exception: {exc}")
        return runner

    def db_port_open() -> CheckResult:
        ok, msg = check_tcp(postgres_host, postgres_port)
        return CheckResult("db_port_open", "db", ok, msg)

    def db_sql_probe_optional() -> CheckResult:
        dsn = (
            f"host={postgres_host} port={postgres_port} dbname={get_env('POSTGRES_DB', 'fsi_risk', file_env)} "
            f"user={get_env('POSTGRES_USER', 'postgres', file_env)} password={get_env('POSTGRES_PASSWORD', 'postgres', file_env)}"
        )
        try:
            import psycopg  # type: ignore

            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT MAX(evaluate_date)
                        FROM fsi.balance_portfolio_nav
                        WHERE port_id = %s
                        """,
                        (args.fund_id,),
                    )
                    row = cur.fetchone()
            return CheckResult("db_sql_probe_optional", "db", True, "sql probe ok", detail=f"max evaluate_date={row[0] if row else None}")
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                "db_sql_probe_optional",
                "db",
                False,
                "sql probe failed (install psycopg or verify DB auth)",
                detail=str(exc),
            )

    def processing_health() -> CheckResult:
        status, payload = http_json("GET", f"{processing_base}/health")
        ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
        return CheckResult("processing_health", "processing", ok, f"status={status}", detail=str(payload)[:300])

    def processing_context() -> CheckResult:
        status, payload = http_json(
            "GET",
            f"{processing_base}/context",
            headers={"X-API-Key": processing_key},
        )
        ok = status == 200 and isinstance(payload, dict) and "funds" in payload
        return CheckResult("processing_context", "processing", ok, f"status={status}", detail=str(payload)[:300])

    def processing_exposure_latest() -> CheckResult:
        status, payload = http_json(
            "GET",
            f"{processing_base}/risk/exposure-latest-date/{args.fund_id}",
            headers={"X-API-Key": processing_key},
            params={"as_of_date": args.as_of_date},
        )
        ok = status == 200 and isinstance(payload, dict) and "effective_date" in payload
        return CheckResult("processing_exposure_latest", "processing", ok, f"status={status}", detail=str(payload)[:300])

    def processing_exposure() -> CheckResult:
        status, payload = http_json(
            "GET",
            f"{processing_base}/risk/exposure/{args.fund_id}",
            headers={"X-API-Key": processing_key},
            params={"as_of_date": args.as_of_date},
        )
        ok = status == 200 and isinstance(payload, dict) and "total_nav_hkd" in payload
        return CheckResult("processing_exposure", "processing", ok, f"status={status}", detail=str(payload)[:300])

    def mcp_gateway_port_open() -> CheckResult:
        ok, msg = check_tcp("localhost", mcp_gateway_port)
        return CheckResult("mcp_gateway_port_open", "mcp", ok, msg)

    def backend_health() -> CheckResult:
        status, payload = http_json("GET", f"{backend_base}/api/v1/utils/health-check/")
        ok = status == 200 and (payload is True or payload == "true")
        return CheckResult("backend_health", "backend", ok, f"status={status}", detail=str(payload))

    def backend_login() -> CheckResult:
        status, payload = http_json(
            "POST",
            f"{backend_base}/api/v1/login/access-token",
            form_body={"username": admin_email, "password": admin_password},
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if token:
            token_holder["access_token"] = token
        ok = status == 200 and bool(token)
        return CheckResult("backend_login", "backend", ok, f"status={status}", detail=("token issued" if ok else str(payload)[:300]))

    def backend_exposure_latest() -> CheckResult:
        token = token_holder.get("access_token")
        if not token:
            return CheckResult("backend_exposure_latest", "backend", False, "missing token (run backend_login first)")
        status, payload = http_json(
            "GET",
            f"{backend_base}/api/v1/fsi/risk/exposure-latest-date/{args.fund_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"as_of_date": args.as_of_date},
        )
        ok = status == 200 and isinstance(payload, dict) and "effective_date" in payload
        return CheckResult("backend_exposure_latest", "backend", ok, f"status={status}", detail=str(payload)[:300])

    def backend_exposure() -> CheckResult:
        token = token_holder.get("access_token")
        if not token:
            return CheckResult("backend_exposure", "backend", False, "missing token (run backend_login first)")
        status, payload = http_json(
            "GET",
            f"{backend_base}/api/v1/fsi/risk/exposure/{args.fund_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"as_of_date": args.as_of_date},
        )
        ok = status == 200 and isinstance(payload, dict) and "total_nav_hkd" in payload
        return CheckResult("backend_exposure", "backend", ok, f"status={status}", detail=str(payload)[:300])

    def frontend_home() -> CheckResult:
        status, body = http_text(frontend_base)
        ok = status == 200 and "<html" in body.lower()
        return CheckResult("frontend_home", "frontend", ok, f"status={status}", detail=body[:120])

    mapping = {
        "db_port_open": wrap("db_port_open", "db", db_port_open),
        "db_sql_probe_optional": wrap("db_sql_probe_optional", "db", db_sql_probe_optional),
        "processing_health": wrap("processing_health", "processing", processing_health),
        "processing_context": wrap("processing_context", "processing", processing_context),
        "processing_exposure_latest": wrap("processing_exposure_latest", "processing", processing_exposure_latest),
        "processing_exposure": wrap("processing_exposure", "processing", processing_exposure),
        "mcp_gateway_port_open": wrap("mcp_gateway_port_open", "mcp", mcp_gateway_port_open),
        "backend_health": wrap("backend_health", "backend", backend_health),
        "backend_login": wrap("backend_login", "backend", backend_login),
        "backend_exposure_latest": wrap("backend_exposure_latest", "backend", backend_exposure_latest),
        "backend_exposure": wrap("backend_exposure", "backend", backend_exposure),
        "frontend_home": wrap("frontend_home", "frontend", frontend_home),
    }
    order = [
        "db_port_open",
        "db_sql_probe_optional",
        "processing_health",
        "processing_context",
        "processing_exposure_latest",
        "processing_exposure",
        "mcp_gateway_port_open",
        "backend_health",
        "backend_login",
        "backend_exposure_latest",
        "backend_exposure",
        "frontend_home",
    ]

    checks: list[Callable[[], CheckResult]] = [mapping[name] for name in order]
    if args.only:
        checks = [mapping[name] for name in args.only if name in mapping]

    results: list[CheckResult] = []
    for check in checks:
        result = check()
        results.append(result)

    passed = sum(1 for item in results if item.ok)
    failed = len(results) - passed

    if args.json:
        print(json.dumps({
            "fund_id": args.fund_id,
            "as_of_date": args.as_of_date,
            "passed": passed,
            "failed": failed,
            "results": [item.__dict__ for item in results],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Dataflow checks: passed={passed}, failed={failed}")
        for item in results:
            status = "PASS" if item.ok else "FAIL"
            print(f"[{status}] {item.name} ({item.layer}) - {item.message}")
            if item.detail:
                print(f"       detail: {item.detail}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
