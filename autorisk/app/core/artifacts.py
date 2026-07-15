from __future__ import annotations

import html
import json
from pathlib import Path

from .conclusion import build_assessment_conclusion
from .crypto import sha256_payload
from .reporting import render_report_markdown
from ..schemas import AssessmentConclusion, ReportArtifact, RiskEvalReport


class ArtifactWriter:
    """Materialize structured JSON, Markdown and print-ready HTML reports."""

    def __init__(self, output_dir: Path, validity_minutes: int = 60):
        self.output_dir = output_dir
        self.validity_minutes = validity_minutes
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, report: RiskEvalReport) -> list[ReportArtifact]:
        report_dir = self.output_dir / report.report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json", exclude={"artifacts"})
        markdown = render_report_markdown(payload)
        html_text = self._render_html(markdown, report)
        contents = {
            "json": json.dumps(payload, ensure_ascii=False, indent=2),
            "md": markdown,
            "html": html_text,
        }

        artifacts: list[ReportArtifact] = []
        for fmt, content in contents.items():
            path = report_dir / f"{report.report_id}.{fmt}"
            path.write_text(content, encoding="utf-8")
            artifacts.append(
                ReportArtifact(
                    format=fmt,
                    path=f"{report.report_id}/{path.name}",
                    sha256=sha256_payload(content),
                )
            )
        artifacts.extend(self.write_conclusion(report))
        return artifacts

    def write_conclusion(self, report: RiskEvalReport) -> list[ReportArtifact]:
        report_dir = self.output_dir / report.report_id
        report_dir.mkdir(parents=True, exist_ok=True)
        conclusion = build_assessment_conclusion(
            report,
            validity_minutes=self.validity_minutes,
        )
        contents = {
            "conclusion-json": (
                f"{report.report_id}.conclusion.json",
                json.dumps(conclusion.model_dump(mode="json"), ensure_ascii=False, indent=2),
            ),
            "conclusion-html": (
                f"{report.report_id}.conclusion.html",
                self._render_conclusion_html(conclusion),
            ),
        }
        artifacts: list[ReportArtifact] = []
        for fmt, (filename, content) in contents.items():
            path = report_dir / filename
            path.write_text(content, encoding="utf-8")
            artifacts.append(
                ReportArtifact(
                    format=fmt,
                    path=f"{report.report_id}/{filename}",
                    sha256=sha256_payload(content),
                )
            )
        return artifacts

    @staticmethod
    def _render_html(markdown: str, report: RiskEvalReport) -> str:
        escaped = html.escape(markdown)
        color = {"GREEN": "#15803d", "YELLOW": "#a16207", "RED": "#b91c1c"}[report.severity.value]
        return f"""<!doctype html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<title>{html.escape(report.report_id)} 風控評估報告</title>
<style>
body{{font-family:Arial,'Microsoft JhengHei',sans-serif;margin:40px;color:#172033}}
header{{border-bottom:4px solid {color};padding-bottom:16px;margin-bottom:24px}}
.badge{{display:inline-block;background:{color};color:white;padding:6px 12px;border-radius:16px}}
pre{{white-space:pre-wrap;line-height:1.65;font-family:inherit}}
footer{{margin-top:32px;border-top:1px solid #ddd;padding-top:12px;color:#64748b;font-size:12px}}
@media print{{body{{margin:18mm}}}}
</style>
</head>
<body>
<header><h1>AutoRisk 風控評估報告</h1><span class="badge">{report.severity.value}</span></header>
<pre>{escaped}</pre>
<footer>內容哈希：{html.escape(report.content_hash)} · 本頁可使用瀏覽器列印為 PDF</footer>
</body>
</html>"""

    @staticmethod
    def _render_conclusion_html(conclusion: AssessmentConclusion) -> str:
        directive = conclusion.directive
        color = {
            "PROCEED": "#087f5b",
            "PROCEED_WITH_CONTROLS": "#b26a00",
            "DO_NOT_PROCEED": "#c92a2a",
        }[directive.action.value]
        instructions = "".join(
            f"<li>{html.escape(item)}</li>" for item in directive.instructions
        )
        restrictions = "".join(
            f"<li>{html.escape(item)}</li>" for item in directive.restrictions
        ) or "<li>無額外限制</li>"
        approvals = "".join(
            "<tr>"
            f"<td>{html.escape(item.signer_role.value)}</td>"
            f"<td>{html.escape(item.signer_id)}</td>"
            f"<td>{html.escape(item.decision.value)}</td>"
            f"<td>{html.escape(item.signed_at.isoformat())}</td>"
            "</tr>"
            for item in conclusion.approvals
        ) or '<tr><td colspan="4">待簽署</td></tr>'
        return f"""<!doctype html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<title>{html.escape(conclusion.certificate_id)} AI 風控結論單</title>
<style>
*{{box-sizing:border-box}}body{{font-family:Arial,'Microsoft JhengHei',sans-serif;margin:0;background:#eef2f5;color:#172033}}
.sheet{{width:210mm;min-height:297mm;margin:18px auto;background:#fff;padding:16mm;box-shadow:0 10px 40px #17203322}}
header{{display:flex;justify-content:space-between;border-bottom:3px solid #172033;padding-bottom:14px}}
h1{{margin:0;font-size:26px}}.sub{{color:#64748b;font-size:12px;letter-spacing:1.4px}}.id{{text-align:right;font-size:12px}}
.decision{{margin:24px 0;border:3px solid {color};padding:22px;text-align:center;background:{color}0d}}
.decision b{{display:block;color:{color};font-size:36px;margin-bottom:8px}}.decision p{{margin:0;line-height:1.7}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px 24px;margin:20px 0}}.field{{border-bottom:1px solid #dbe2e8;padding:8px 0}}
.field span{{display:block;color:#64748b;font-size:11px}}.field strong{{font-size:14px}}
h2{{font-size:16px;border-left:4px solid {color};padding-left:9px;margin-top:24px}}li{{margin:7px 0;line-height:1.55}}
table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{border:1px solid #dbe2e8;padding:8px;text-align:left}}
.hash{{word-break:break-all;background:#f6f8fa;padding:12px;font:11px Consolas,monospace}}
.notice{{margin-top:20px;padding:12px;border:1px solid #dbe2e8;color:#475569;font-size:12px;line-height:1.6}}
footer{{margin-top:28px;border-top:1px solid #dbe2e8;padding-top:10px;color:#64748b;font-size:10px}}
@media print{{body{{background:#fff}}.sheet{{margin:0;box-shadow:none;width:auto;min-height:auto}}}}
</style>
</head>
<body><main class="sheet">
<header><div><div class="sub">AUTORISK · AI RISK DECISION CERTIFICATE</div><h1>AI 風控審核結論單</h1></div><div class="id">結論單編號<br><strong>{html.escape(conclusion.certificate_id)}</strong></div></header>
<section class="decision"><b>{html.escape(directive.headline)}</b><p>{html.escape(directive.summary)}</p></section>
<section class="grid">
<div class="field"><span>基金</span><strong>{html.escape(conclusion.fund_code)} / {html.escape(conclusion.fund_name)}</strong></div>
<div class="field"><span>請求編號</span><strong>{html.escape(conclusion.request_id)}</strong></div>
<div class="field"><span>風險等級</span><strong>{html.escape(conclusion.severity.value)}</strong></div>
<div class="field"><span>執行決策</span><strong>{html.escape(conclusion.execution_decision.value)}</strong></div>
<div class="field"><span>簽發時間</span><strong>{html.escape(conclusion.issued_at.isoformat())}</strong></div>
<div class="field"><span>有效至</span><strong>{html.escape(conclusion.valid_until.isoformat())}</strong></div>
</section>
<h2>處置指令</h2><ol>{instructions}</ol>
<h2>限制與風險命中</h2><ul>{restrictions}</ul>
<h2>兩級覆核簽署</h2><table><thead><tr><th>角色</th><th>簽署者</th><th>結論</th><th>時間</th></tr></thead><tbody>{approvals}</tbody></table>
<h2>驗證信息</h2><div class="hash">Report SHA-256: {html.escape(conclusion.verification.report_content_hash)}<br>Certificate SHA-256: {html.escape(conclusion.verification.certificate_hash)}</div>
<div class="notice">{html.escape(conclusion.validity_note)}</div>
<footer>此結論單由 AutoRisk 規則引擎與兩級 AI 覆核流程生成。下游處置後須提交 JSON 回執；本頁可使用瀏覽器列印為 PDF。</footer>
</main></body></html>"""
