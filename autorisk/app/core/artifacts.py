from __future__ import annotations

import html
import json
from pathlib import Path

from .crypto import sha256_payload
from .reporting import render_report_markdown
from ..schemas import ReportArtifact, RiskEvalReport


class ArtifactWriter:
    """Materialize structured JSON, Markdown and print-ready HTML reports."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
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
