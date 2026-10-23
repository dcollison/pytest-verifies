"""Single-file, zero-dependency HTML5 reporter for Requirements Traceability Matrix."""

from __future__ import annotations

import html
import json
from pathlib import Path

from pytest_verifies.models import RTMReport


def generate_html_report(report: RTMReport, output_path: str | Path | None = None) -> str:
    """Generate a self-contained, interactive HTML5 RTM report document.

    Args:
        report: The consolidated RTMReport instance.
        output_path: Optional file path to write the HTML artefact.

    Returns:
        str: Valid HTML5 document source string.
    """
    total_reqs = report.total_baseline_requirements or report.total_observed_requirements
    pass_pct = f"{report.coverage_percentage:.1f}%"
    failed_pct = f"{(report.failed_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"
    partial_pct = (
        f"{(report.partial_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"
    )
    orphan_pct = f"{(report.orphan_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"

    has_stages = report.has_stages
    rows_html: list[str] = []

    for req in report.requirements:
        display_status = req.display_status
        status_lower = display_status.lower()

        is_orphan_cls = " is-orphan" if req.is_orphan else ""
        row_classes = f"req-row status-{status_lower}{is_orphan_cls}"

        stages_rendered = (
            ", ".join(
                f'<span class="stage-tag stage-{s_status.lower()}">{html.escape(stage)}: {html.escape(s_status)}</span>'
                for stage, s_status in sorted(req.stages_verified.items())
            )
            if req.stages_verified
            else "—"
        )
        stages_cell = f'<td class="col-stages">{stages_rendered}</td>' if has_stages else ""

        test_count = len(req.verified_by_tests)
        tests_label = f"{test_count} passing test(s)" if test_count > 0 else "—"

        # Details expansion content
        details_html = []

        if req.failure_messages:
            details_html.append('<div class="detail-failures"><b>Failure Diagnostics:</b>')
            for msg in req.failure_messages:
                details_html.append(f'<pre class="code-box failure-box">{html.escape(msg)}</pre>')
            details_html.append("</div>")

        if req.evidence:
            evidence_json = json.dumps(req.evidence, indent=2, default=str)
            details_html.append(
                f'<div class="detail-evidence"><b>Objective Evidence:</b><pre class="code-box evidence-box">{html.escape(evidence_json)}</pre></div>'
            )

        if req.records:
            details_html.append(
                '<div class="detail-records"><b>Execution Trace:</b><ul class="trace-list">'
            )
            for r in req.records:
                dur = f"{r.duration_s:.4f}s"
                step_badge = (
                    f' <span class="badge badge-step">Step: {html.escape(r.step_id)}</span>'
                    if r.step_id
                    else ""
                )
                details_html.append(
                    f'<li><code>{html.escape(r.nodeid)}</code>{step_badge} <span class="badge badge-{r.status.lower()}">{r.status}</span> '
                    f"at <code>{html.escape(r.location)}</code> ({dur})</li>"
                )
            details_html.append("</ul></div>")

        details_block = (
            f'<div class="details-content">{"".join(details_html)}</div>' if details_html else ""
        )

        badge_extra = '<span class="badge badge-orphan">ORPHAN</span>' if req.is_orphan else ""

        rows_html.append(f"""
        <tr class="{row_classes}" data-status="{status_lower}" data-orphan="{"true" if req.is_orphan else "false"}">
          <td class="col-id">
            <details>
              <summary><code>{html.escape(req.req_id)}</code></summary>
              {details_block}
            </details>
          </td>
          <td class="col-text">{html.escape(req.text) or "<em>(No text)</em>"}</td>
          <td class="col-status">
            <span class="badge badge-{status_lower}">{display_status}</span>
            {badge_extra}
          </td>
          <td class="col-baseline">{"Yes" if req.in_baseline else "No"}</td>
          {stages_cell}
          <td class="col-tests">{tests_label}</td>
        </tr>
        """)

    table_rows = "".join(rows_html)

    action_records = [r for r in report.test_records if r.is_action]
    action_section_html = ""
    if action_records:
        action_rows = []
        for ar in action_records:
            ev_html = ""
            if ar.evidence:
                ev_json = json.dumps(ar.evidence, indent=2, default=str)
                ev_html = f'<details><summary>Evidence</summary><pre class="code-box evidence-box">{html.escape(ev_json)}</pre></details>'
            elif ar.message:
                ev_html = f'<pre class="code-box failure-box">{html.escape(ar.message)}</pre>'
            else:
                ev_html = "—"

            action_rows.append(f"""
            <tr>
              <td><code>{html.escape(ar.step_id or "")}</code></td>
              <td><code>{html.escape(ar.nodeid)}</code></td>
              <td><span class="badge badge-{ar.status.lower()}">{ar.status}</span></td>
              <td>{html.escape(ar.description or "") or "—"}</td>
              <td>{ar.duration_s:.4f}s</td>
              <td>{ev_html}</td>
            </tr>
            """)

        action_section_html = f"""
        <div style="margin-top: 2rem;">
          <h2 style="font-size: 1.1rem; font-weight: 600; color: var(--text); margin-bottom: 0.75rem;">
            Test Procedure Action Steps
          </h2>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>Step ID</th>
                  <th>Test</th>
                  <th>Status</th>
                  <th>Description</th>
                  <th>Duration</th>
                  <th>Evidence / Details</th>
                </tr>
              </thead>
              <tbody>
                {"".join(action_rows)}
              </tbody>
            </table>
          </div>
        </div>
        """

    document = f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Requirements Traceability Matrix</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --green: #22c55e;
      --green-bg: rgba(34, 197, 94, 0.15);
      --red: #ef4444;
      --red-bg: rgba(239, 68, 68, 0.15);
      --amber: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.15);
      --gray: #64748b;
      --gray-bg: rgba(100, 116, 139, 0.15);
      --code-bg: #090d16;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 2rem;
    }}
    .container {{ max-width: 1300px; margin: 0 auto; }}
    header {{ margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }}
    h1 {{ font-size: 2rem; font-weight: 700; color: var(--text); margin-bottom: 0.25rem; }}
    .timestamp {{ color: var(--text-muted); font-size: 0.875rem; }}

    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
    }}
    .card-label {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }}
    .card-value {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
    .card-pct {{ font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem; }}

    .card-verified .card-value, .card-pass .card-value {{ color: var(--green); }}
    .card-failed .card-value, .card-fail .card-value {{ color: var(--red); }}
    .card-partial .card-value {{ color: var(--amber); }}
    .card-unverified .card-value {{ color: var(--text-muted); }}
    .card-orphan .card-value {{ color: var(--amber); }}
    .card-coverage .card-value {{ color: var(--primary); }}

    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
    }}
    .filters {{ display: flex; gap: 0.5rem; }}
    .btn {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.4rem 0.8rem;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      transition: all 0.15s ease-in-out;
    }}
    .btn:hover, .btn.active {{
      background: var(--primary);
      color: #020617;
      border-color: var(--primary);
      font-weight: 600;
    }}
    .search-box {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.375rem;
      padding: 0.4rem 0.8rem;
      color: var(--text);
      font-size: 0.875rem;
      width: 280px;
    }}
    .search-box:focus {{ outline: 2px solid var(--primary); border-color: transparent; }}

    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.875rem;
    }}
    th, td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{
      background: #182234;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.05em;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

    .badge {{
      display: inline-block;
      padding: 0.15rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.03em;
    }}
    .badge-pass, .badge-verified, .badge-passed {{ background: var(--green-bg); color: var(--green); }}
    .badge-fail, .badge-failed, .badge-error, .badge-xfailed {{ background: var(--red-bg); color: var(--red); }}
    .badge-partial {{ background: var(--amber-bg); color: var(--amber); }}
    .badge-unverified, .badge-skipped {{ background: var(--gray-bg); color: var(--text-muted); }}
    .badge-orphan {{ background: var(--amber-bg); color: var(--amber); margin-left: 0.25rem; }}
    .badge-step {{ background: rgba(56, 189, 248, 0.15); color: var(--primary); margin-left: 0.25rem; font-family: ui-monospace, monospace; }}
    .badge-xpass {{ background: var(--green-bg); color: var(--green); }}

    .stage-tag {{
      display: inline-block;
      font-size: 0.75rem;
      padding: 0.1rem 0.4rem;
      border-radius: 0.25rem;
      margin-right: 0.25rem;
      background: #0f172a;
      border: 1px solid var(--border);
    }}
    .stage-tag.stage-pass, .stage-tag.stage-verified {{ border-color: var(--green); color: var(--green); }}
    .stage-tag.stage-fail, .stage-tag.stage-failed {{ border-color: var(--red); color: var(--red); }}
    .stage-tag.stage-partial {{ border-color: var(--amber); color: var(--amber); }}

    details summary {{
      cursor: pointer;
      color: var(--primary);
      user-select: none;
      font-weight: 600;
    }}
    details summary:hover {{ text-decoration: underline; }}
    .details-content {{
      margin-top: 0.75rem;
      padding: 0.75rem;
      background: var(--code-bg);
      border-radius: 0.375rem;
      border: 1px solid var(--border);
      max-width: 900px;
    }}
    .code-box {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.8rem;
      padding: 0.5rem;
      border-radius: 0.25rem;
      overflow-x: auto;
      margin-top: 0.25rem;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .failure-box {{ background: #2b1114; border: 1px solid #7f1d1d; color: #fca5a5; }}
    .evidence-box {{ background: #0c1e28; border: 1px solid #0369a1; color: #7dd3fc; }}
    .trace-list {{ margin-left: 1.25rem; margin-top: 0.25rem; font-size: 0.8rem; }}
    .detail-desc {{ margin-bottom: 0.5rem; font-size: 0.85rem; color: var(--text); }}
    .detail-failures, .detail-evidence, .detail-records {{ margin-top: 0.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Requirements Traceability Matrix</h1>
      <div class="timestamp">Generated: {html.escape(report.generated_at)}</div>
    </header>

    <div class="cards-grid">
      <div class="card card-coverage">
        <span class="card-label">Pass Coverage</span>
        <span class="card-value">{pass_pct}</span>
        <span class="card-pct">{report.passed_count} of {total_reqs} reqs</span>
      </div>
      <div class="card card-pass">
        <span class="card-label">Pass</span>
        <span class="card-value">{report.passed_count}</span>
        <span class="card-pct">{pass_pct}</span>
      </div>
      <div class="card card-partial">
        <span class="card-label">Partial</span>
        <span class="card-value">{report.partial_count}</span>
        <span class="card-pct">{partial_pct}</span>
      </div>
      <div class="card card-fail">
        <span class="card-label">Fail</span>
        <span class="card-value">{report.failed_count}</span>
        <span class="card-pct">{failed_pct}</span>
      </div>
      <div class="card card-orphan">
        <span class="card-label">Orphans</span>
        <span class="card-value">{report.orphan_count}</span>
        <span class="card-pct">{orphan_pct}</span>
      </div>
    </div>

    <div class="toolbar">
      <div class="filters">
        <button class="btn active" data-filter="all">All ({len(report.requirements)})</button>
        <button class="btn" data-filter="pass">Pass ({report.passed_count})</button>
        <button class="btn" data-filter="partial">Partial ({report.partial_count})</button>
        <button class="btn" data-filter="fail">Fail ({report.failed_count})</button>
        <button class="btn" data-filter="orphan">Orphans ({report.orphan_count})</button>
      </div>
      <input type="text" id="searchInput" class="search-box" placeholder="Filter by ID, Text, or Test..." />
    </div>

    <div class="table-container">
      <table id="requirementsTable">
        <thead>
          <tr>
            <th>Requirement ID</th>
            <th>Requirement Text</th>
            <th>Status</th>
            <th>In Baseline</th>
            {("<th>Stages</th>" if has_stages else "")}
            <th>Verified By Tests</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
    {action_section_html}
  </div>

  <script>
    (function() {{
      const filterBtns = document.querySelectorAll('.filters .btn');
      const searchInput = document.getElementById('searchInput');
      const rows = document.querySelectorAll('#requirementsTable tbody tr');
      let currentFilter = 'all';

      function applyFilter() {{
        const search = searchInput.value.toLowerCase().trim();

        rows.forEach(row => {{
          const status = row.getAttribute('data-status');
          const isOrphan = row.getAttribute('data-orphan') === 'true';
          const text = row.textContent.toLowerCase();

          let matchesFilter = false;
          if (currentFilter === 'all') {{
            matchesFilter = true;
          }} else if (currentFilter === 'orphan') {{
            matchesFilter = isOrphan;
          }} else {{
            matchesFilter = (status === currentFilter);
          }}

          const matchesSearch = !search || text.includes(search);

          if (matchesFilter && matchesSearch) {{
            row.style.display = '';
          }} else {{
            row.style.display = 'none';
          }}
        }});
      }}

      filterBtns.forEach(btn => {{
        btn.addEventListener('click', () => {{
          filterBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          currentFilter = btn.getAttribute('data-filter');
          applyFilter();
        }});
      }});

      searchInput.addEventListener('input', applyFilter);
    }})();
  </script>
</body>
</html>
"""
    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(document, encoding="utf-8")
    return document
