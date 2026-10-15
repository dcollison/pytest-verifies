"""Markdown reporter for Requirements Traceability Matrix artefacts."""

from __future__ import annotations

import html
import json
from pathlib import Path

from pytest_verifies.models import RTMReport


def generate_markdown_report(report: RTMReport, output_path: str | Path | None = None) -> str:
    """Generate a GitHub Step Summary and PR-ready Markdown document.

    Args:
        report: The consolidated RTMReport instance.
        output_path: Optional file path to write the Markdown artefact.

    Returns:
        str: Formatted Markdown text.
    """
    lines: list[str] = []

    lines.append("# Requirements Traceability Matrix (RTM)")
    lines.append("")
    lines.append(f"*Generated at: {report.generated_at}*")
    lines.append("")

    # Summary Scorecard Table
    lines.append("## Summary Scorecard")
    lines.append("")
    lines.append("| Metric | Count | Percentage |")
    lines.append("| :--- | :--- | :--- |")

    total_reqs = report.total_baseline_requirements or report.total_observed_requirements
    lines.append(f"| **Total Requirements** | {total_reqs} | 100.0% |")

    v_pct = f"{report.coverage_percentage:.1f}%"
    lines.append(f"| **Verified** | {report.verified_count} | {v_pct} |")

    f_pct = f"{(report.failed_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"
    lines.append(f"| **Failed** | {report.failed_count} | {f_pct} |")

    u_pct = f"{(report.unverified_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"
    lines.append(f"| **Unverified** | {report.unverified_count} | {u_pct} |")

    o_pct = f"{(report.orphan_count / total_reqs * 100.0):.1f}%" if total_reqs > 0 else "0.0%"
    lines.append(f"| **Orphans** | {report.orphan_count} | {o_pct} |")
    lines.append("")

    # Requirements Traceability Table
    lines.append("## Requirements Traceability")
    lines.append("")
    lines.append("| Requirement ID | Title | Status | In Baseline | Stages | Verified By Tests |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    for req in report.requirements:
        if req.status == "FAILED":
            status_badge = "FAILED"
        elif req.status == "VERIFIED":
            is_partial = any(s == "UNVERIFIED" for s in req.stages_verified.values()) or any(
                r.status == "SKIPPED" for r in req.records
            )
            status_badge = "PARTIAL" if is_partial else "VERIFIED"
        else:
            status_badge = "UNVERIFIED"

        if req.is_orphan:
            status_badge += " [ORPHAN]"

        title_display = req.title if req.title else "*(No title)*"
        in_base_display = "Yes" if req.in_baseline else "No"
        stages_display = (
            ", ".join(
                f"`{stage}: {status}`" for stage, status in sorted(req.stages_verified.items())
            )
            if req.stages_verified
            else "—"
        )
        tests_display = f"{len(req.verified_by_tests)} test(s)" if req.verified_by_tests else "—"

        lines.append(
            f"| `{req.req_id}` | {title_display} | {status_badge} | {in_base_display} | {stages_display} | {tests_display} |"
        )
    lines.append("")

    # Evidence and Failure Details Section
    has_details = any(req.failure_messages or req.evidence for req in report.requirements)
    if has_details:
        lines.append("## Verification Details & Objective Evidence")
        lines.append("")

        for req in report.requirements:
            if not req.failure_messages and not req.evidence:
                continue

            lines.append("<details>")
            lines.append(
                f"<summary><b>{html.escape(req.req_id)}</b> — {html.escape(req.title or req.status)}</summary>"
            )
            lines.append("")

            if req.description:
                lines.append(f"> {html.escape(req.description)}")
                lines.append("")

            if req.failure_messages:
                lines.append("#### Failure Diagnostics:")
                lines.append("```")
                for msg in req.failure_messages:
                    lines.append(msg)
                lines.append("```")
                lines.append("")

            if req.evidence:
                lines.append("#### Objective Evidence:")
                lines.append("```json")
                lines.append(json.dumps(req.evidence, indent=2))
                lines.append("```")
                lines.append("")

            if req.records:
                lines.append("#### Test Locations:")
                for r in req.records:
                    lines.append(
                        f"- `{r.nodeid}` [{r.status}] at `{r.location}` ({r.duration_s:.4f}s)"
                    )
                lines.append("")

            lines.append("</details>")
            lines.append("")

    content = "\n".join(lines) + "\n"
    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return content
