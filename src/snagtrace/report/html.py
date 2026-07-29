from __future__ import annotations

from html import escape

from ..core import DiagnosisResult

_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>snagtrace report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; background: #F4F5F3; color: #191D1A; margin: 0; padding: 40px; }}
  h1 {{ font-size: 22px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #D8DBD6; text-align: left; padding: 8px 10px; }}
  th {{ text-transform: uppercase; font-size: 11px; color: #4B534E; }}
  .healthy {{ color: #2F6B44; font-weight: 600; }}
  .first {{ background: #F7E9E7; }}
  .warn {{ color: #8A6415; font-size: 13px; }}
</style>
</head>
<body>
<h1>snagtrace report</h1>
{body}
</body>
</html>
"""


def render_html(result: DiagnosisResult) -> str:
    warnings_html = ""
    if result.has_detector_errors:
        items = "".join(f"<li>{escape(str(e))}</li>" for e in result.errors)
        warnings_html = f'<p class="warn">{len(result.errors)} detector(s) failed and were skipped:</p><ul class="warn">{items}</ul>'

    if result.is_healthy:
        return _TEMPLATE.format(body=warnings_html + '<p class="healthy">No faults detected.</p>')

    first = result.first_fault
    rows = []
    for f in sorted(result.faults, key=lambda x: x.step_id):
        cls = ' class="first"' if first and f.step_id == first.step_id else ""
        rows.append(
            f"<tr{cls}><td>{f.step_id}</td><td>{escape(f.category)}</td>"
            f"<td>{f.confidence:.2f}</td><td>{escape(f.detector)}</td>"
            f"<td>{escape(f.evidence)}</td></tr>"
        )

    body = (
        warnings_html
        + f"<p><strong>{len(result.faults)}</strong> fault(s) found. "
        f"First fault at step <strong>{first.step_id}</strong> "
        f"(<code>{escape(first.category)}</code>).</p>"
        "<table><thead><tr><th>Step</th><th>Category</th><th>Confidence</th>"
        "<th>Detector</th><th>Evidence</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
    return _TEMPLATE.format(body=body)
