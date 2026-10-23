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

    has_stages = report.has_stages

    # Calculate required column widths dynamically so columns NEVER overflow or misalign
    id_width = max(20, max((len(r.req_id) for r in report.requirements), default=20))

    formatted_rows: list[tuple[str, str, dict[str, bool], str, str, str]] = []
    status_texts: list[str] = []
    stages_texts: list[str] = []

    for req in report.requirements:
        st = req.display_status
        if req.is_orphan:
            st += " [ORPHAN]"
        status_texts.append(st)

        if has_stages:
            stages_str = (
                ", ".join(f"{s}:{st_val}" for s, st_val in sorted(req.stages_verified.items()))
                or "-"
            )
            if len(stages_str) > 28:
                stages_str = stages_str[:25] + "..."
            stages_texts.append(stages_str)
        else:
            stages_str = ""

        if st.startswith("FAIL"):
            status_color: dict[str, bool] = {"red": True, "bold": True}
        elif st.startswith("PARTIAL"):
            status_color = {"yellow": True, "bold": True}
        elif st.startswith("PASS"):
            status_color = {"green": True, "bold": True}
        else:
            status_color = {"cyan": True}

        test_count_str = str(len(req.verified_by_tests))
        formatted_rows.append(
            (req.req_id, st, status_color, stages_str, test_count_str, req.text or "")
        )

    status_width = max(10, max((len(st) for st in status_texts), default=10))

    if has_stages:
        stages_width = max(15, max((len(st) for st in stages_texts), default=15))
        header = (
            f"{'Requirement ID':<{id_width}} {'Status':<{status_width}} "
            f"{'Stages':<{stages_width}} {'Tests':>5}  Requirement Text"
        )
    else:
        stages_width = 0
        header = f"{'Requirement ID':<{id_width}} {'Status':<{status_width}} {'Tests':>5}  Requirement Text"

    sep_fn("=", "Requirements Traceability Matrix (RTM)", bold=True)
    line_fn(header, bold=True)
    line_fn("-" * len(header))

    for req_id, st, status_color, stages_str, test_count_str, text in formatted_rows:
        write_fn(f"{req_id:<{id_width}} ")
        write_fn(f"{st:<{status_width}} ", **status_color)
        if has_stages:
            write_fn(f"{stages_str:<{stages_width}} ")
        write_fn(f"{test_count_str:>5}  ")
        line_fn(text)

    line_fn("-" * len(header))
    total_reqs = report.total_baseline_requirements or report.total_observed_requirements
    p_pct = f"{report.coverage_percentage:.1f}%"
    write_fn(f"Total: {total_reqs} | ")
    write_fn(f"Pass: {report.passed_count} ({p_pct}) | ", green=True, bold=True)
    write_fn(
        f"Fail: {report.failed_count} | ",
        red=(report.failed_count > 0),
        bold=(report.failed_count > 0),
    )
    write_fn(
        f"Partial: {report.partial_count} | ",
        yellow=(report.partial_count > 0),
        bold=(report.partial_count > 0),
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
