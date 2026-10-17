"""Command-line interface for pytest-verifies.

Provides the standalone `pytest-verifies combine` command to merge execution shards,
validate against baseline manifests, evaluate quality gates, and output reports.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from pytest_verifies.baseline import load_baseline
from pytest_verifies.models import BaselineRequirement, RTMReport
from pytest_verifies.reporters import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
)
from pytest_verifies.storage import consolidate_requirements, read_shards


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="pytest-verifies",
        description="Enterprise requirements traceability matrix tool for pytest.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # `combine` subcommand
    combine_parser = subparsers.add_parser(
        "combine",
        help="Combine multiple execution shards and generate traceability reports.",
    )
    combine_parser.add_argument(
        "shards",
        nargs="+",
        help="One or more shard file paths (.jsonl) or directories containing shards.",
    )
    combine_parser.add_argument(
        "--baseline",
        "-b",
        type=str,
        default=None,
        help="Path to baseline requirements manifest (.json, .csv, .yaml).",
    )
    combine_parser.add_argument(
        "--json",
        type=str,
        default=None,
        help="Path to generate structured JSON report.",
    )
    combine_parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to generate tabular CSV report.",
    )
    combine_parser.add_argument(
        "--md",
        type=str,
        default=None,
        help="Path to generate Markdown summary report.",
    )
    combine_parser.add_argument(
        "--html",
        type=str,
        default=None,
        help="Path to generate interactive HTML5 report.",
    )
    combine_parser.add_argument(
        "--disallow-orphans",
        action="store_true",
        default=False,
        help="Fail quality gate if observed requirements are not in the baseline.",
    )
    combine_parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Minimum required verified requirement coverage percentage (0.0 to 100.0).",
    )
    combine_parser.add_argument(
        "--color",
        choices=["yes", "no", "auto"],
        default="auto",
        help="Control colour formatting in terminal output (default: auto).",
    )

    return parser


def combine_command(args: argparse.Namespace) -> int:
    """Execute the combine subcommand to merge shards and verify quality gates.

    Returns:
        int: Exit status code (0 for success, 1 for quality gate failure).
    """
    baseline_map: dict[str, BaselineRequirement] | None = None
    if args.baseline:
        try:
            baseline_map = load_baseline(args.baseline)
        except Exception as exc:
            print(f"Error loading baseline manifest '{args.baseline}': {exc}", file=sys.stderr)
            return 1

    runs, records = read_shards(args.shards)
    if not records and not runs:
        print(
            f"Warning: No valid verification records found in specified paths: {args.shards}",
            file=sys.stderr,
        )

    report: RTMReport = consolidate_requirements(records, baseline=baseline_map, runs=runs)

    # Output requested reports
    if args.json:
        generate_json_report(report, args.json)
        print(f"Generated JSON report: {args.json}")
    if args.csv:
        generate_csv_report(report, args.csv)
        print(f"Generated CSV report: {args.csv}")
    if args.md:
        generate_markdown_report(report, args.md)
        print(f"Generated Markdown report: {args.md}")
    if args.html:
        generate_html_report(report, args.html)
        print(f"Generated HTML report: {args.html}")

    # Display console summary using TerminalWriter
    from _pytest._io.terminalwriter import TerminalWriter

    tw = TerminalWriter(sys.stdout)
    if getattr(args, "color", "auto") == "yes":
        tw.hasmarkup = True
    elif getattr(args, "color", "auto") == "no":
        tw.hasmarkup = False

    tw.sep("=", "Requirements Traceability Matrix (RTM)", bold=True)
    header = f"{'Requirement ID':<20} {'Status':<12} {'Stages':<22} {'Tests':>5}  Requirement Text"
    tw.line(header, bold=True)
    tw.line("-" * len(header))

    partial_count = 0
    for req in report.requirements:
        if req.status == "FAILED":
            status_text = "FAILED"
            status_color = {"red": True, "bold": True}
        elif req.status == "VERIFIED":
            is_partial = any(s == "UNVERIFIED" for s in req.stages_verified.values()) or any(
                r.status == "SKIPPED" for r in req.records
            )
            if is_partial:
                status_text = "PARTIAL"
                status_color = {"yellow": True, "bold": True}
                partial_count += 1
            else:
                status_text = "VERIFIED"
                status_color = {"green": True, "bold": True}
        else:
            status_text = "UNVERIFIED"
            status_color = {"cyan": True}

        if req.is_orphan:
            status_text += " [ORPHAN]"

        stages_str = ", ".join(f"{s}:{st}" for s, st in sorted(req.stages_verified.items())) or "-"
        if len(stages_str) > 21:
            stages_str = stages_str[:18] + "..."

        test_count_str = str(len(req.verified_by_tests))

        tw.write(f"{req.req_id:<20} ")
        tw.write(f"{status_text:<12} ", **status_color)
        tw.write(f"{stages_str:<22} ")
        tw.write(f"{test_count_str:>5}  ")
        tw.line(req.text or "")

    tw.line("-" * len(header))
    total_reqs = report.total_baseline_requirements or report.total_observed_requirements
    v_pct = f"{report.coverage_percentage:.1f}%"
    tw.write(f"Total: {total_reqs} | ")
    tw.write(f"Verified: {report.verified_count} ({v_pct}) | ", green=True, bold=True)
    tw.write(
        f"Failed: {report.failed_count} | ",
        red=(report.failed_count > 0),
        bold=(report.failed_count > 0),
    )
    tw.write(
        f"Partial: {partial_count} | ",
        yellow=(partial_count > 0),
        bold=(partial_count > 0),
    )
    tw.write(
        f"Unverified: {report.unverified_count} | ",
        cyan=(report.unverified_count > 0),
    )
    tw.line(
        f"Orphans: {report.orphan_count}",
        yellow=(report.orphan_count > 0),
    )
    tw.sep("=", bold=True)

    # Quality Gate Checks
    exit_code = 0

    # 1. Any requirement with consolidated status FAILED
    failed_reqs = [r.req_id for r in report.requirements if r.status == "FAILED"]
    if failed_reqs:
        print(
            f"Quality gate failure: {len(failed_reqs)} requirement(s) failed: {', '.join(failed_reqs)}",
            file=sys.stderr,
        )
        exit_code = 1

    # 2. Disallow orphans check
    if args.disallow_orphans and report.orphan_count > 0:
        orphan_ids = [r.req_id for r in report.requirements if r.is_orphan]
        print(
            f"Quality gate failure: Found {len(orphan_ids)} orphaned requirement(s) not in baseline: {', '.join(orphan_ids)}",
            file=sys.stderr,
        )
        exit_code = 1

    # 3. Minimum coverage percentage threshold
    if args.fail_under is not None:
        if report.coverage_percentage < args.fail_under:
            print(
                f"Quality gate failure: Coverage {report.coverage_percentage:.1f}% is below threshold of {args.fail_under:.1f}%",
                file=sys.stderr,
            )
            exit_code = 1

    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args_list = list(argv if argv is not None else sys.argv[1:])

    # Ergonomic fallback: if first argument is not a known subcommand and not help, default to combine
    if args_list and args_list[0] not in ("combine", "-h", "--help"):
        args_list.insert(0, "combine")
    elif not args_list:
        parser.print_help()
        return 0

    args = parser.parse_args(args_list)
    if args.subcommand == "combine":
        return combine_command(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
