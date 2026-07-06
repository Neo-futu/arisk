"""Runtime report writer used by 5_deploy orchestrator.

This module performs real report generation (markdown + xlsx) under artefacts/.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def generate_risk_report(
    fund_id: str,
    as_of_date: str,
    risk_result: dict[str, Any],
    positions_data: dict[str, Any],
    output_dir: str = "artefacts",
) -> dict[str, Any]:
    """Generate markdown and xlsx report files and return paths and summary."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{fund_id}_{as_of_date}_risk_report"
    xlsx_path = out_dir / f"{stem}.xlsx"
    md_path = out_dir / f"{stem}.md"

    _write_markdown(md_path, fund_id, as_of_date, risk_result)
    _write_xlsx(xlsx_path, fund_id, as_of_date, risk_result, positions_data)

    primary_var = risk_result.get("primary_var", {})
    summary = (
        f"Risk report for {fund_id} on {as_of_date}. "
        f"Compliant: {risk_result.get('is_compliant')}. "
        f"Primary VaR: {float(primary_var.get('var_pct_nav', 0.0) or 0.0):.2f}% NAV"
    )

    return {
        "artefact_path": str(xlsx_path).replace("\\", "/"),
        "artefact_url": xlsx_path.resolve().as_uri(),
        "markdown_path": str(md_path).replace("\\", "/"),
        "summary": summary,
    }


def _write_markdown(path: Path, fund_id: str, as_of_date: str, risk_result: dict[str, Any]) -> None:
    exposure = risk_result.get("exposure", {})
    var_results = risk_result.get("var_results", [])

    lines = [
        f"# Risk Report - {fund_id}",
        "",
        f"- As Of Date: {as_of_date}",
        f"- Generated At: {datetime.utcnow().isoformat()}Z",
        f"- Is Compliant: {exposure.get('is_compliant', True)}",
        f"- WAM (days): {exposure.get('wam_days', 'N/A')}",
        f"- WAL (days): {exposure.get('wal_days', 'N/A')}",
        f"- Daily Liquid (%): {exposure.get('daily_liquid_pct', 'N/A')}",
        f"- Weekly Liquid (%): {exposure.get('weekly_liquid_pct', 'N/A')}",
        "",
        "## VaR Comparison",
        "",
        "| Method | VaR (HKD) | VaR (%NAV) | CVaR (HKD) | Sample Size |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in var_results:
        lines.append(
            "| {method} | {var_hkd:.2f} | {var_pct_nav:.4f} | {cvar_hkd:.2f} | {sample_size} |".format(
                method=row.get("method", row.get("method_requested", "UNKNOWN")),
                var_hkd=float(row.get("var_hkd", 0.0) or 0.0),
                var_pct_nav=float(row.get("var_pct_nav", 0.0) or 0.0),
                cvar_hkd=float(row.get("cvar_hkd", 0.0) or 0.0),
                sample_size=int(row.get("sample_size", 0) or 0),
            )
        )

    breach_flags = list((risk_result.get("breach_flags") or {}).keys())
    lines.extend([
        "",
        "## Breaches",
        "",
    ])
    if breach_flags:
        lines.extend([f"- {flag}" for flag in breach_flags])
    else:
        lines.append("- None")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_xlsx(
    path: Path,
    fund_id: str,
    as_of_date: str,
    risk_result: dict[str, Any],
    positions_data: dict[str, Any],
) -> None:
    wb = Workbook()

    # Sheet 1: Risk summary
    ws = wb.active
    ws.title = "risk_summary"

    exposure = risk_result.get("exposure", {})
    ws.append(["fund_id", fund_id])
    ws.append(["as_of_date", as_of_date])
    ws.append(["generated_at_utc", f"{datetime.utcnow().isoformat()}Z"])
    ws.append(["is_compliant", exposure.get("is_compliant", True)])
    ws.append(["wam_days", exposure.get("wam_days", "N/A")])
    ws.append(["wal_days", exposure.get("wal_days", "N/A")])
    ws.append(["daily_liquid_pct", exposure.get("daily_liquid_pct", "N/A")])
    ws.append(["weekly_liquid_pct", exposure.get("weekly_liquid_pct", "N/A")])
    ws.append(["max_var_pct_nav", risk_result.get("max_var_pct_nav", 0.0)])

    # Sheet 2: VaR methods
    var_sheet = wb.create_sheet("var_methods")
    var_sheet.append(["method", "method_requested", "var_hkd", "var_pct_nav", "cvar_hkd", "sample_size"])
    for row in risk_result.get("var_results", []):
        var_sheet.append([
            row.get("method"),
            row.get("method_requested"),
            float(row.get("var_hkd", 0.0) or 0.0),
            float(row.get("var_pct_nav", 0.0) or 0.0),
            float(row.get("cvar_hkd", 0.0) or 0.0),
            int(row.get("sample_size", 0) or 0),
        ])

    # Sheet 3: data-puller summary snapshot
    positions_sheet = wb.create_sheet("positions_snapshot")
    positions_sheet.append(["key", "value"])
    if isinstance(positions_data, dict):
        for key, value in positions_data.items():
            if isinstance(value, (dict, list, tuple)):
                positions_sheet.append([key, str(value)[:5000]])
            else:
                positions_sheet.append([key, value])

    wb.save(path)
