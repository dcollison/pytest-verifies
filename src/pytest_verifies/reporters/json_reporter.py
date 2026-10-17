"""JSON reporter for Requirements Traceability Matrix artefacts."""

from __future__ import annotations

import json
from pathlib import Path

from pytest_verifies.models import RTMReport


def generate_json_report(report: RTMReport, output_path: str | Path | None = None) -> str:
    """Generate a structured JSON representation of the RTM report.

    Args:
        report: The consolidated RTMReport instance.
        output_path: Optional file path to write the JSON artefact.

    Returns:
        str: Pretty-printed JSON string.
    """
    content = json.dumps(report.to_dict(), indent=2, default=str)
    if output_path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return content
