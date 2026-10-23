"""CSV reporter for Requirements Traceability Matrix artefacts."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pytest_verifies.models import RTMReport


def generate_csv_report(report: RTMReport, output_path: str | Path | None = None) -> str:
    """Generate a tabular CSV representation of the RTM report.

    Header schema:
    req_id,text,status,in_baseline,stages,steps,verified_by_tests,evidence,failure_messages

    Args:
        report: The consolidated RTMReport instance.
        output_path: Optional file path to write the CSV artefact.

    Returns:
        str: Comma-separated values text.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    # Header row
    writer.writerow(
        [
            "req_id",
            "text",
            "status",
            "in_baseline",
            "stages",
            "steps",
            "verified_by_tests",
            "evidence",
            "failure_messages",
        ]
    )

    for req in report.requirements:
        stages_str = "; ".join(
            f"{stage}:{status}" for stage, status in sorted(req.stages_verified.items())
        )
        steps_str = "; ".join(req.steps)
        tests_str = "; ".join(req.verified_by_tests)
        evidence_str = json.dumps(req.evidence, default=str) if req.evidence else ""
        failures_str = " | ".join(
            msg.replace("\n", " ").strip() for msg in req.failure_messages if msg
        )

        writer.writerow(
            [
                req.req_id,
                req.text,
                req.status,
                "TRUE" if req.in_baseline else "FALSE",
                stages_str,
                steps_str,
                tests_str,
                evidence_str,
                failures_str,
            ]
        )

    content = buffer.getvalue()
    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return content
