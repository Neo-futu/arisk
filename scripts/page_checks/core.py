from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"


@dataclass
class CheckResult:
    name: str
    layer: str
    ok: bool
    message: str
    detail: str = ""


@dataclass
class CheckContext:
    file_env: dict[str, str]
    backend_base: str
    processing_base: str
    frontend_base: str
    autorisk_base: str
    processing_key: str
    admin_email: str
    admin_password: str
    postgres_host: str
    postgres_port: int
    mcp_gateway_port: int
    fund_id: str
    as_of_date: str
    start_date: str
    end_date: str
    report_id: str
    access_token: str | None = None


def load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def get_env(key: str, default: str, env_file: dict[str, str]) -> str:
    return os.getenv(key) or env_file.get(key) or default


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
        url = f"{url}{'&' if '?' in url else '?'}{query}"

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
    req = urllib.request.Request(url=url, method="GET", headers={"Accept": "text/html,*/*"})
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


def try_get_latest_nav_date(ctx: CheckContext) -> str | None:
    dsn = (
        f"host={ctx.postgres_host} port={ctx.postgres_port} "
        f"dbname={get_env('POSTGRES_DB', 'fsi_risk', ctx.file_env)} "
        f"user={get_env('POSTGRES_USER', 'postgres', ctx.file_env)} "
        f"password={get_env('POSTGRES_PASSWORD', 'postgres', ctx.file_env)}"
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
                    (ctx.fund_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
    except Exception:
        return None
    return None


def build_context(args: argparse.Namespace) -> CheckContext:
    file_env = load_env_file(ENV_PATH)
    backend_base = get_env("BACKEND_PUBLIC_URL", "http://localhost:8000", file_env).rstrip("/")
    processing_base = get_env("PROCESSING_API_URL", "http://localhost:8001", file_env).rstrip("/")
    frontend_base = get_env("FRONTEND_HOST", "http://localhost:5173", file_env).rstrip("/")
    autorisk_base = get_env("VITE_AUTORISK_URL", "http://localhost:8100", file_env).rstrip("/")
    processing_key = get_env("PROCESSING_API_KEY", "internal_key_change_me", file_env)
    admin_email = get_env("FIRST_SUPERUSER", "admin@fsi.com", file_env)
    admin_password = get_env("FIRST_SUPERUSER_PASSWORD", "changethis", file_env)

    postgres_host = get_env("POSTGRES_SERVER", get_env("POSTGRES_HOST", "localhost", file_env), file_env)
    postgres_port = int(get_env("POSTGRES_PORT", "5432", file_env))
    mcp_gateway_port = int(get_env("MCP_GATEWAY_PORT", "8002", file_env))

    as_of_date = args.as_of_date or last_trade_date_text()
    start_date = args.start_date
    end_date = args.end_date

    ctx = CheckContext(
        file_env=file_env,
        backend_base=backend_base,
        processing_base=processing_base,
        frontend_base=frontend_base,
        autorisk_base=autorisk_base,
        processing_key=processing_key,
        admin_email=admin_email,
        admin_password=admin_password,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        mcp_gateway_port=mcp_gateway_port,
        fund_id=args.fund_id,
        as_of_date=as_of_date,
        start_date=start_date or as_of_date,
        end_date=end_date or as_of_date,
        report_id=args.report_id,
    )

    latest = try_get_latest_nav_date(ctx)
    if latest and not args.as_of_date:
        ctx.as_of_date = latest
        ctx.end_date = latest
        if not args.start_date:
            d = dt.date.fromisoformat(latest) - dt.timedelta(days=30)
            ctx.start_date = d.isoformat()

    if not args.start_date:
        try:
            d = dt.date.fromisoformat(ctx.end_date) - dt.timedelta(days=30)
            ctx.start_date = d.isoformat()
        except Exception:
            pass

    return ctx


def make_result(name: str, layer: str, ok: bool, message: str, detail: str = "") -> CheckResult:
    return CheckResult(name=name, layer=layer, ok=ok, message=message, detail=detail)


def base_checks(ctx: CheckContext, route_path: str, include_mcp: bool = True) -> list[CheckResult]:
    results: list[CheckResult] = []

    ok, msg = check_tcp(ctx.postgres_host, ctx.postgres_port)
    results.append(make_result("db_port_open", "db", ok, msg))

    latest = try_get_latest_nav_date(ctx)
    results.append(make_result("db_latest_nav_date", "db", bool(latest), "latest date resolved" if latest else "latest date unavailable", latest or ""))

    status, payload = http_json("GET", f"{ctx.processing_base}/health")
    ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    results.append(make_result("processing_health", "processing", ok, f"status={status}", str(payload)[:300]))

    status, payload = http_json("GET", f"{ctx.backend_base}/api/v1/utils/health-check/")
    ok = status == 200 and (payload is True or payload == "true")
    results.append(make_result("backend_health", "backend", ok, f"status={status}", str(payload)[:300]))

    status, payload = http_json(
        "POST",
        f"{ctx.backend_base}/api/v1/login/access-token",
        form_body={"username": ctx.admin_email, "password": ctx.admin_password},
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    ctx.access_token = token
    results.append(make_result("backend_login", "backend", status == 200 and bool(token), f"status={status}", "token issued" if token else str(payload)[:300]))

    if include_mcp:
        ok, msg = check_tcp("localhost", ctx.mcp_gateway_port)
        results.append(make_result("mcp_gateway_port_open", "mcp", ok, msg))

    route_url = f"{ctx.frontend_base}{route_path}"
    status, body = http_text(route_url)
    ok = status == 200 and "<html" in body.lower()
    results.append(make_result("frontend_route", "frontend", ok, f"status={status}", route_url))

    return results


def check_processing_get(
    ctx: CheckContext,
    name: str,
    path: str,
    params: dict[str, str],
    expect_keys: list[str],
) -> CheckResult:
    status, payload = http_json(
        "GET",
        f"{ctx.processing_base}{path}",
        headers={"X-API-Key": ctx.processing_key},
        params=params,
    )
    ok = status == 200 and isinstance(payload, dict) and all(key in payload for key in expect_keys)
    return make_result(name, "processing", ok, f"status={status}", str(payload)[:300])


def check_backend_get(
    ctx: CheckContext,
    name: str,
    path: str,
    params: dict[str, str],
    expect_keys: list[str],
) -> CheckResult:
    token = ctx.access_token
    if not token:
        return make_result(name, "backend", False, "missing token", "run backend_login first")
    status, payload = http_json(
        "GET",
        f"{ctx.backend_base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    ok = status == 200 and isinstance(payload, dict) and all(key in payload for key in expect_keys)
    return make_result(name, "backend", ok, f"status={status}", str(payload)[:300])


def check_backend_post(
    ctx: CheckContext,
    name: str,
    path: str,
    body: dict,
    expect_keys: list[str],
) -> CheckResult:
    token = ctx.access_token
    if not token:
        return make_result(name, "backend", False, "missing token", "run backend_login first")
    status, payload = http_json(
        "POST",
        f"{ctx.backend_base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json_body=body,
    )
    ok = status in (200, 201, 202) and isinstance(payload, dict) and all(key in payload for key in expect_keys)
    return make_result(name, "backend", ok, f"status={status}", str(payload)[:300])


def check_backend_simple_get(ctx: CheckContext, name: str, path: str, params: dict[str, str] | None = None) -> CheckResult:
    token = ctx.access_token
    if not token:
        return make_result(name, "backend", False, "missing token", "run backend_login first")
    status, payload = http_json(
        "GET",
        f"{ctx.backend_base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    ok = status == 200
    return make_result(name, "backend", ok, f"status={status}", str(payload)[:300])


def run_report(results: list[CheckResult], args: argparse.Namespace) -> int:
    passed = sum(1 for item in results if item.ok)
    failed = len(results) - passed

    if args.json:
        print(json.dumps({
            "passed": passed,
            "failed": failed,
            "results": [asdict(item) for item in results],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Page checks: passed={passed}, failed={failed}")
        for item in results:
            status = "PASS" if item.ok else "FAIL"
            print(f"[{status}] {item.name} ({item.layer}) - {item.message}")
            if item.detail:
                print(f"       detail: {item.detail}")

    return 0 if failed == 0 else 1


def page_dashboard(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/")
    params = {"as_of_date": ctx.as_of_date}
    out.append(check_processing_get(ctx, "processing_exposure_latest", f"/risk/exposure-latest-date/{ctx.fund_id}", params, ["effective_date"]))
    out.append(check_processing_get(ctx, "processing_exposure", f"/risk/exposure/{ctx.fund_id}", params, ["total_nav_hkd"]))
    out.append(check_backend_get(ctx, "backend_exposure_latest", f"/api/v1/fsi/risk/exposure-latest-date/{ctx.fund_id}", params, ["effective_date"]))
    out.append(check_backend_get(ctx, "backend_exposure", f"/api/v1/fsi/risk/exposure/{ctx.fund_id}", params, ["total_nav_hkd"]))
    return out


def page_investment_home(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk")
    params = {"as_of_date": ctx.as_of_date}
    out.append(check_processing_get(ctx, "processing_overview", f"/investment/overview/{ctx.fund_id}", params, ["portfolio"]))
    out.append(check_backend_get(ctx, "backend_overview", f"/api/v1/fsi/investment/overview/{ctx.fund_id}", params, ["portfolio"]))
    return out


def page_investment_overview(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/overview")
    params1 = {"as_of_date": ctx.as_of_date}
    params2 = {"start": ctx.start_date, "end": ctx.end_date}
    out.append(check_processing_get(ctx, "processing_overview", f"/investment/overview/{ctx.fund_id}", params1, ["portfolio"]))
    out.append(check_processing_get(ctx, "processing_overview_timeseries", f"/investment/overview-timeseries/{ctx.fund_id}", params2, ["points"]))
    out.append(check_backend_get(ctx, "backend_overview", f"/api/v1/fsi/investment/overview/{ctx.fund_id}", params1, ["portfolio"]))
    out.append(check_backend_get(ctx, "backend_overview_timeseries", f"/api/v1/fsi/investment/overview-timeseries/{ctx.fund_id}", params2, ["points"]))
    return out


def page_investment_indicators(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/indicators")
    params_range = {"start": ctx.start_date, "end": ctx.end_date}
    params_asof = {"as_of_date": ctx.as_of_date}
    params_var = {"as_of_date": ctx.as_of_date, "method": "historical", "confidence": "0.99", "horizon_days": "1"}
    out.append(check_processing_get(ctx, "processing_risk_indicators", f"/investment/risk-indicators/{ctx.fund_id}", params_range, ["sample_size"]))
    out.append(check_processing_get(ctx, "processing_risk_ts", f"/investment/risk-indicators-timeseries/{ctx.fund_id}", params_range, ["points"]))
    out.append(check_processing_get(ctx, "processing_var", f"/risk/var/{ctx.fund_id}", params_var, ["var_hkd", "method"]))
    out.append(check_backend_get(ctx, "backend_risk_indicators", f"/api/v1/fsi/investment/risk-indicators/{ctx.fund_id}", params_range, ["sample_size"]))
    out.append(check_backend_get(ctx, "backend_risk_ts", f"/api/v1/fsi/investment/risk-indicators-timeseries/{ctx.fund_id}", params_range, ["points"]))
    out.append(check_backend_get(ctx, "backend_var_compare", f"/api/v1/fsi/risk/var-compare/{ctx.fund_id}", params_asof, ["results"]))
    return out


def page_investment_attribution(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/attribution")
    params = {"start": ctx.start_date, "end": ctx.end_date}
    out.append(check_processing_get(ctx, "processing_attribution", f"/investment/attribution/{ctx.fund_id}", params, ["summary"]))
    out.append(check_processing_get(ctx, "processing_attribution_ts", f"/investment/attribution-timeseries/{ctx.fund_id}", params, ["cumulative_points"]))
    out.append(check_backend_get(ctx, "backend_attribution", f"/api/v1/fsi/investment/attribution/{ctx.fund_id}", params, ["summary"]))
    out.append(check_backend_get(ctx, "backend_attribution_ts", f"/api/v1/fsi/investment/attribution-timeseries/{ctx.fund_id}", params, ["cumulative_points"]))
    return out


def page_investment_rates_credit(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/rates-credit")
    params = {"as_of_date": ctx.as_of_date}
    out.append(check_processing_get(ctx, "processing_rates_credit", f"/investment/rates-credit/{ctx.fund_id}", params, ["portfolio_dv01", "rating_distribution"]))
    out.append(check_backend_get(ctx, "backend_rates_credit", f"/api/v1/fsi/investment/rates-credit/{ctx.fund_id}", params, ["portfolio_dv01", "rating_distribution"]))
    return out


def page_investment_liquidity_stress(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/liquidity-stress")
    params = {"as_of_date": ctx.as_of_date, "redemption_pct": "20", "rate_shock_bps": "50"}
    out.append(check_processing_get(ctx, "processing_liquidity_stress", f"/investment/liquidity-stress/{ctx.fund_id}", params, ["stress_summary", "breach_flags"]))
    out.append(check_backend_get(ctx, "backend_liquidity_stress", f"/api/v1/fsi/investment/liquidity-stress/{ctx.fund_id}", params, ["stress_summary", "breach_flags"]))
    return out


def page_investment_pretrade_budget(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/pretrade-budget")
    params = {
        "as_of_date": ctx.as_of_date,
        "trade_amount": "100000",
        "trade_side": "BUY",
        "asset_class": "Bond",
        "duration_years": "1.5",
        "issuer_name": "TEST_ISSUER",
    }
    out.append(check_processing_get(ctx, "processing_pretrade", f"/investment/pretrade-check/{ctx.fund_id}", params, ["trade", "projected"]))
    out.append(check_backend_get(ctx, "backend_pretrade", f"/api/v1/fsi/investment/pretrade-check/{ctx.fund_id}", params, ["trade", "projected"]))
    return out


def page_investment_macro_dynamics(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/macro-dynamics")
    params = {"start": ctx.start_date, "end": ctx.end_date}
    out.append(check_processing_get(ctx, "processing_macro", f"/investment/macro-dynamics/{ctx.fund_id}", params, ["fund_id"]))
    out.append(check_backend_get(ctx, "backend_macro", f"/api/v1/fsi/investment/macro-dynamics/{ctx.fund_id}", params, ["fund_id"]))
    return out


def page_investment_factor_behavior(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/investment-risk/factor-behavior")
    params = {"start": ctx.start_date, "end": ctx.end_date}
    out.append(check_processing_get(ctx, "processing_factor_behavior", f"/investment/factor-behavior/{ctx.fund_id}", params, ["fund_id"]))
    out.append(check_backend_get(ctx, "backend_factor_behavior", f"/api/v1/fsi/investment/factor-behavior/{ctx.fund_id}", params, ["fund_id"]))
    return out


def page_positions(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/positions")
    params = {"as_of_date": ctx.as_of_date}
    out.append(check_processing_get(ctx, "processing_positions", f"/positions/{ctx.fund_id}", params, ["count", "positions"]))
    out.append(check_backend_get(ctx, "backend_positions", f"/api/v1/fsi/positions/{ctx.fund_id}", params, ["count", "positions"]))
    return out


def page_compliance(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/compliance")
    params = {"as_of_date": ctx.as_of_date}
    out.append(check_processing_get(ctx, "processing_exposure", f"/risk/exposure/{ctx.fund_id}", params, ["is_compliant", "breach_flags"]))
    out.append(check_backend_get(ctx, "backend_exposure", f"/api/v1/fsi/risk/exposure/{ctx.fund_id}", params, ["is_compliant", "breach_flags"]))
    return out


def page_reports(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/reports")
    params = {"fund_id": ctx.fund_id, "as_of_date": ctx.as_of_date}
    out.append(check_backend_simple_get(ctx, "backend_report_result", f"/api/v1/fsi/reports/result/{ctx.report_id}", params=params))
    body = {"report_id": ctx.report_id, "fund_id": ctx.fund_id, "as_of_date": ctx.as_of_date}
    out.append(check_backend_post(ctx, "backend_generate_report", "/api/v1/fsi/reports/generate", body, ["task_id", "status"]))
    return out


def page_schedules(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/schedules")
    out.append(check_backend_simple_get(ctx, "backend_list_schedules", "/api/v1/fsi/schedules/"))
    return out


def page_autorisk(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/autorisk")
    status, payload = http_json("GET", f"{ctx.autorisk_base}/health")
    ok = status == 200 and isinstance(payload, dict)
    out.append(make_result("autorisk_health", "autorisk", ok, f"status={status}", str(payload)[:300]))
    return out


def page_chat(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/chat")
    out.append(check_backend_simple_get(ctx, "backend_agents", "/api/v1/fsi/agent/v2/agents"))
    out.append(check_backend_simple_get(ctx, "backend_models", "/api/v1/fsi/agent/v2/models"))
    out.append(check_backend_simple_get(ctx, "backend_chat_sessions", "/api/v1/chat/sessions"))
    return out


def page_expert(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/expert")
    out.append(check_backend_simple_get(ctx, "backend_knowledge_documents", "/api/v1/knowledge/documents", params={"limit": "20"}))
    out.append(check_backend_simple_get(ctx, "backend_models", "/api/v1/fsi/agent/v2/models"))
    return out


def page_admin(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/admin")
    out.append(check_backend_simple_get(ctx, "backend_users_list", "/api/v1/users/", params={"skip": "0", "limit": "50"}))
    out.append(check_backend_simple_get(ctx, "backend_user_me", "/api/v1/users/me"))
    return out


def page_api_keys(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/api-keys")
    out.append(check_backend_simple_get(ctx, "backend_api_keys", "/api/v1/api-keys/"))
    out.append(check_backend_simple_get(ctx, "backend_local_api_config", "/api/v1/api-keys/local-config"))
    return out


def page_notifications(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/notifications")
    out.append(check_backend_simple_get(ctx, "backend_notification_channels", "/api/v1/notifications/channels"))
    return out


def page_settings(ctx: CheckContext) -> list[CheckResult]:
    out = base_checks(ctx, "/settings")
    out.append(check_backend_simple_get(ctx, "backend_user_me", "/api/v1/users/me"))
    return out


PAGE_RUNNERS: dict[str, Callable[[CheckContext], list[CheckResult]]] = {
    "dashboard": page_dashboard,
    "investment_home": page_investment_home,
    "investment_overview": page_investment_overview,
    "investment_indicators": page_investment_indicators,
    "investment_attribution": page_investment_attribution,
    "investment_rates_credit": page_investment_rates_credit,
    "investment_liquidity_stress": page_investment_liquidity_stress,
    "investment_pretrade_budget": page_investment_pretrade_budget,
    "investment_macro_dynamics": page_investment_macro_dynamics,
    "investment_factor_behavior": page_investment_factor_behavior,
    "positions": page_positions,
    "compliance": page_compliance,
    "reports": page_reports,
    "schedules": page_schedules,
    "autorisk": page_autorisk,
    "chat": page_chat,
    "expert": page_expert,
    "admin": page_admin,
    "api_keys": page_api_keys,
    "notifications": page_notifications,
    "settings": page_settings,
}


def build_parser(page_name: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Run page-level dataflow checks: {page_name}")
    parser.add_argument("--fund-id", default="BHMMF001")
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--report-id", default="report_03_mmf")
    parser.add_argument("--json", action="store_true")
    return parser


def run_named_page(page_name: str) -> int:
    if page_name not in PAGE_RUNNERS:
        print(f"Unknown page key: {page_name}")
        return 2
    parser = build_parser(page_name)
    args = parser.parse_args()
    ctx = build_context(args)
    try:
        results = PAGE_RUNNERS[page_name](ctx)
    except Exception as exc:  # noqa: BLE001
        results = [make_result("runner_exception", "script", False, f"exception: {exc}")]
    return run_report(results, args)
