"""Requirements Traceability Matrix reporters for JSON, CSV, Markdown, and HTML formats."""

from __future__ import annotations

from typing import Any

from pytest_verifies.models import RTMReport
from pytest_verifies.reporters.csv_reporter import generate_csv_report
from pytest_verifies.reporters.html_reporter import generate_html_report
from pytest_verifies.reporters.json_reporter import generate_json_report
from pytest_verifies.reporters.markdown_reporter import generate_markdown_report


def render_console_summary(report: RTMReport, writer: Any) -> None:
    """Render a coloured console RTM summary table using a pytest TerminalReporter or TerminalWriter."""
    sep_fn = getattr(writer, "write_sep", None) or writer.sep
    line_fn = getattr(writer, "write_line", None) or writer.line
    write_fn = writer.write

    sep_fn("=", "Requirements Traceability Matrix (RTM)", bold=True)
    header = f"{'Requirement ID':<20} {'Status':<12} {'Stages':<22} {'Tests':>5}  Requirement Text"
    line_fn(header, bold=True)
    line_fn("-" * len(header))

    for req in report.requirements:
        status_text = req.display_status
        if status_text == "FAILED":
            status_color: dict[str, bool] = {"red": True, "bold": True}
        elif status_text == "PARTIAL":
            status_color = {"yellow": True, "bold": True}
        elif status_text == "VERIFIED":
            status_color = {"green": True, "bold": True}
        else:
            status_color = {"cyan": True}

        if req.is_orphan:
            status_text += " [ORPHAN]"

        stages_str = ", ".join(f"{s}:{st}" for s, st in sorted(req.stages_verified.items())) or "-"
        if len(stages_str) > 21:
            stages_str = stages_str[:18] + "..."

        test_count_str = str(len(req.verified_by_tests))

        write_fn(f"{req.req_id:<20} ")
        write_fn(f"{status_text:<12} ", **status_color)
        write_fn(f"{stages_str:<22} ")
        write_fn(f"{test_count_str:>5}  ")
        line_fn(req.text or "")

    partial_count = report.partial_count
    line_fn("-" * len(header))
    total_reqs = report.total_baseline_requirements or report.total_observed_requirements
    v_pct = f"{report.coverage_percentage:.1f}%"
    write_fn(f"Total: {total_reqs} | ")
    write_fn(f"Verified: {report.verified_count} ({v_pct}) | ", green=True, bold=True)
    write_fn(
        f"Failed: {report.failed_count} | ",
        red=(report.failed_count > 0),
        bold=(report.failed_count > 0),
    )
    write_fn(
        f"Partial: {partial_count} | ",
        yellow=(partial_count > 0),
        bold=(partial_count > 0),
    )
    write_fn(
        f"Unverified: {report.unverified_count} | ",
        cyan=(report.unverified_count > 0),
    )
    line_fn(
        f"Orphans: {report.orphan_count}",
        yellow=(report.orphan_count > 0),
    )
    sep_fn("=", bold=True)


__all__ = [
    "generate_json_report",
    "generate_csv_report",
    "generate_markdown_report",
    "generate_html_report",
    "render_console_summary",
]
