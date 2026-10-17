"""Pytest plugin hooks for requirements traceability.

Implements CLI options, collection filtering, AST analysis, execution recording,
xdist-safe property transmission, shard persistence, and quality gate evaluations.
"""

from __future__ import annotations

import ast
import fnmatch
import inspect
import textwrap
from datetime import datetime, timezone
from typing import Any, Generator

import pytest

from pytest_verifies.baseline import load_baseline
from pytest_verifies.context import (
    _active_records,
    _current_test_nodeid,
    _current_test_stage,
    _global_soft,
    _soft_failures,
)
from pytest_verifies.models import BaselineRequirement, VerificationRecord
from pytest_verifies.reporters import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
)
from pytest_verifies.storage import consolidate_requirements, write_shard


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI flags and ini configuration options for requirements traceability."""
    group = parser.getgroup("verifies", "Requirements Traceability Matrix")

    group.addoption(
        "--req",
        "--verifies-only",
        dest="req",
        action="store",
        default=None,
        help="Comma-separated requirement IDs or glob patterns to filter tests (e.g. 'REQ-001,REQ-AUTH-*').",
    )
    group.addoption(
        "--verifies-out",
        action="store",
        default=None,
        help="Directory path to output JSONL execution shard files.",
    )
    parser.addini(
        "verifies_out",
        "Directory path to output JSONL execution shard files.",
        default=None,
    )
    group.addoption(
        "--verifies-stage",
        action="store",
        default="default",
        help="Test execution stage label (e.g. 'unit', 'integration', 'system'). Default: 'default'.",
    )
    parser.addini(
        "verifies_stage",
        "Test execution stage label.",
        default="default",
    )
    group.addoption(
        "--verifies-baseline",
        action="store",
        default=None,
        help="Path to baseline requirements manifest (.json, .csv, .yaml).",
    )
    parser.addini(
        "verifies_baseline",
        "Path to baseline requirements manifest.",
        default=None,
    )
    group.addoption(
        "--verifies-soft",
        action="store_true",
        default=False,
        help="Enable soft verification mode globally across all verifies blocks.",
    )
    parser.addini(
        "verifies_soft",
        "Enable soft verification globally (type: bool).",
        type="bool",
        default=False,
    )
    group.addoption(
        "--verifies-disallow-orphans",
        action="store_true",
        default=False,
        help="Fail session/collection if tests reference requirement IDs not present in baseline.",
    )
    group.addoption(
        "--verifies-fail-under",
        action="store",
        type=float,
        default=None,
        help="Fail session if verified requirement coverage %% is below this threshold (0.0 to 100.0).",
    )
    group.addoption(
        "--verifies-json",
        action="store",
        default=None,
        help="Direct output path for structured JSON RTM report.",
    )
    group.addoption(
        "--verifies-csv",
        action="store",
        default=None,
        help="Direct output path for tabular CSV RTM report.",
    )
    group.addoption(
        "--verifies-md",
        action="store",
        default=None,
        help="Direct output path for Markdown RTM report.",
    )
    group.addoption(
        "--verifies-html",
        action="store",
        default=None,
        help="Direct output path for interactive HTML5 RTM report.",
    )


def extract_requirements_from_item(item: pytest.Item) -> set[str]:
    """Extract linked requirement IDs from item markers and AST inspection of function body."""
    extracted: set[str] = set()

    # 1. Markers (captures @verifies(...) and pytest.param(..., marks=verifies(...)))
    for marker in item.iter_markers(name="verifies"):
        for arg in marker.args:
            if isinstance(arg, str) and arg.strip():
                extracted.add(arg.strip())
            elif isinstance(arg, (list, tuple, set)):
                for sub in arg:
                    if isinstance(sub, str) and sub.strip():
                        extracted.add(sub.strip())

    # 2. Fast AST inspection of item.obj
    fn = getattr(item, "obj", None)
    if fn is not None and callable(fn):
        try:
            source = inspect.getsource(fn)
            tree = ast.parse(textwrap.dedent(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.With):
                    for with_item in node.items:
                        expr = with_item.context_expr
                        if isinstance(expr, ast.Call):
                            func_name = None
                            if isinstance(expr.func, ast.Name):
                                func_name = expr.func.id
                            elif isinstance(expr.func, ast.Attribute):
                                func_name = expr.func.attr
                            if func_name in ("verifies", "step"):
                                args_to_check = expr.args[1:] if func_name == "step" else expr.args
                                for arg in args_to_check:
                                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                        val = arg.value.strip()
                                        if val:
                                            extracted.add(val)
                                    elif isinstance(arg, (ast.List, ast.Tuple)):
                                        for elt in arg.elts:
                                            if isinstance(elt, ast.Constant) and isinstance(
                                                elt.value, str
                                            ):
                                                val = elt.value.strip()
                                                if val:
                                                    extracted.add(val)
                                for kw in expr.keywords:
                                    if kw.arg in ("req_id", "req_ids", "verifies"):
                                        if isinstance(kw.value, ast.Constant) and isinstance(
                                            kw.value.value, str
                                        ):
                                            val = kw.value.value.strip()
                                            if val:
                                                extracted.add(val)
                                        elif isinstance(kw.value, (ast.List, ast.Tuple)):
                                            for elt in kw.value.elts:
                                                if isinstance(elt, ast.Constant) and isinstance(
                                                    elt.value, str
                                                ):
                                                    val = elt.value.strip()
                                                    if val:
                                                        extracted.add(val)
        except (OSError, TypeError, SyntaxError):
            pass

    item._verifies_req_ids = extracted  # type: ignore[attr-defined]
    return extracted


class VerifiesControllerPlugin:
    """Controller node plugin for aggregating verification records and producing reports."""

    def __init__(
        self,
        config: pytest.Config,
        baseline_map: dict[str, BaselineRequirement] | None,
    ) -> None:
        """Initialise controller plugin instance with configuration and baseline mapping."""
        self.config = config
        self.baseline_map = baseline_map
        self.buffer: list[VerificationRecord] = []

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Harvest verification records from user_properties transmitted by worker or local run."""
        if hasattr(self.config, "workerinput"):
            return

        is_setup_skip_or_fail = report.when == "setup" and (report.skipped or report.failed)
        if report.when != "call" and not is_setup_skip_or_fail:
            return

        for name, value in report.user_properties:
            if name == "verifies_records" and isinstance(value, list):
                for r_dict in value:
                    if isinstance(r_dict, dict):
                        self.buffer.append(VerificationRecord.from_dict(r_dict))

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Write execution shard and evaluate quality gates on the controller node."""
        if hasattr(session.config, "workerinput"):
            return

        # 1. Write execution shard if requested
        out_dir = session.config.getoption("verifies_out") or session.config.getini("verifies_out")
        stage = (
            session.config.getoption("verifies_stage", default="default")
            or session.config.getini("verifies_stage")
            or "default"
        )

        if out_dir:
            write_shard(
                output_dir=out_dir,
                stage=stage,
                records=self.buffer,
            )

        # 2. Check direct reporting flags or quality gate checks
        json_out = session.config.getoption("verifies_json")
        csv_out = session.config.getoption("verifies_csv")
        md_out = session.config.getoption("verifies_md")
        html_out = session.config.getoption("verifies_html")
        fail_under = session.config.getoption("verifies_fail_under")
        disallow_orphans = session.config.getoption("verifies_disallow_orphans")

        has_report_request = bool(
            json_out or csv_out or md_out or html_out or (fail_under is not None)
        )

        if has_report_request:
            report = consolidate_requirements(self.buffer, baseline=self.baseline_map)

            if json_out:
                generate_json_report(report, json_out)
            if csv_out:
                generate_csv_report(report, csv_out)
            if md_out:
                generate_markdown_report(report, md_out)
            if html_out:
                generate_html_report(report, html_out)

            # Evaluate quality gates
            gate_failed = False

            # Gate A: Any requirement FAILED
            if any(r.status == "FAILED" for r in report.requirements):
                gate_failed = True

            # Gate B: Disallow orphans
            if disallow_orphans and report.orphan_count > 0:
                gate_failed = True

            # Gate C: Coverage threshold
            if fail_under is not None and report.coverage_percentage < fail_under:
                gate_failed = True

            if gate_failed:
                session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(
        self,
        terminalreporter: Any,
        exitstatus: int,
        config: pytest.Config,
    ) -> None:
        """Render a clean, coloured console summary table respecting --color options."""
        if hasattr(self.config, "workerinput"):
            return

        # Do not print if no requirements were tracked or baselined
        if not self.buffer and not self.baseline_map:
            return

        report = consolidate_requirements(self.buffer, baseline=self.baseline_map)
        if not report.requirements:
            return

        terminalreporter.write_sep("=", "Requirements Traceability Matrix (RTM)", bold=True)
        header = (
            f"{'Requirement ID':<20} {'Status':<12} {'Stages':<22} {'Tests':>5}  Requirement Text"
        )
        terminalreporter.write_line(header, bold=True)
        terminalreporter.write_line("-" * len(header))

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

            stages_str = (
                ", ".join(f"{s}:{st}" for s, st in sorted(req.stages_verified.items())) or "-"
            )
            if len(stages_str) > 21:
                stages_str = stages_str[:18] + "..."

            test_count_str = str(len(req.verified_by_tests))

            terminalreporter.write(f"{req.req_id:<20} ")
            terminalreporter.write(f"{status_text:<12} ", **status_color)
            terminalreporter.write(f"{stages_str:<22} ")
            terminalreporter.write(f"{test_count_str:>5}  ")
            terminalreporter.write_line(req.text or "")

        terminalreporter.write_line("-" * len(header))
        total_reqs = report.total_baseline_requirements or report.total_observed_requirements
        v_pct = f"{report.coverage_percentage:.1f}%"
        terminalreporter.write(f"Total: {total_reqs} | ")
        terminalreporter.write(
            f"Verified: {report.verified_count} ({v_pct}) | ", green=True, bold=True
        )
        terminalreporter.write(
            f"Failed: {report.failed_count} | ",
            red=(report.failed_count > 0),
            bold=(report.failed_count > 0),
        )
        terminalreporter.write(
            f"Partial: {partial_count} | ",
            yellow=(partial_count > 0),
            bold=(partial_count > 0),
        )
        terminalreporter.write(
            f"Unverified: {report.unverified_count} | ",
            cyan=(report.unverified_count > 0),
        )
        terminalreporter.write_line(
            f"Orphans: {report.orphan_count}",
            yellow=(report.orphan_count > 0),
        )
        terminalreporter.write_sep("=", bold=True)


def pytest_configure(config: pytest.Config) -> None:
    """Register custom marker, load baseline manifest, and register controller listener."""
    config.addinivalue_line(
        "markers",
        "verifies(*req_ids, step=None, step_id=None, description=None, evidence=None): "
        "Link test to formal engineering requirements or procedure steps.",
    )

    baseline_map: dict[str, BaselineRequirement] | None = None
    baseline_path = config.getoption("verifies_baseline") or config.getini("verifies_baseline")
    disallow_orphans = config.getoption("verifies_disallow_orphans")

    if disallow_orphans and not baseline_path:
        raise pytest.UsageError(
            "--verifies-disallow-orphans requires --verifies-baseline to be specified."
        )

    if baseline_path:
        try:
            baseline_map = load_baseline(baseline_path)
            config._verifies_baseline_map = baseline_map  # type: ignore[attr-defined]
        except Exception as exc:
            raise pytest.UsageError(
                f"Failed to load baseline requirements manifest '{baseline_path}': {exc}"
            ) from exc

    # Only register the controller aggregator on controller / master process
    if not hasattr(config, "workerinput"):
        controller = VerifiesControllerPlugin(config, baseline_map)
        config.pluginmanager.register(controller, "verifies_controller")


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Filter tests by requirement patterns and validate baseline orphans."""
    # 1. Static Baseline Orphan Check
    disallow_orphans = config.getoption("verifies_disallow_orphans")
    baseline_map: dict[str, BaselineRequirement] | None = getattr(
        config, "_verifies_baseline_map", None
    )

    if disallow_orphans and baseline_map is not None:
        orphans: list[tuple[str, str]] = []
        for item in items:
            req_ids = extract_requirements_from_item(item)
            for r_id in sorted(req_ids):
                if r_id not in baseline_map:
                    orphans.append((r_id, item.nodeid))
        if orphans:
            details = "\n".join(f"  - {r_id} (referenced in {nid})" for r_id, nid in orphans)
            raise pytest.UsageError(
                f"Found orphaned requirement IDs not present in baseline manifest:\n{details}"
            )

    # 2. Filter tests using --req / --verifies-only
    req_pattern = config.getoption("req")
    if req_pattern:
        patterns = [p.strip() for p in req_pattern.split(",") if p.strip()]
        kept: list[pytest.Item] = []
        deselected: list[pytest.Item] = []

        for item in items:
            raw_reqs = getattr(item, "_verifies_req_ids", None)
            item_req_ids: set[str] = (
                raw_reqs if isinstance(raw_reqs, set) else extract_requirements_from_item(item)
            )

            matches = any(fnmatch.fnmatch(r_id, pat) for r_id in item_req_ids for pat in patterns)
            if matches:
                kept.append(item)
            else:
                deselected.append(item)

        items[:] = kept
        if deselected:
            config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, None]:
    """Execute test call inside isolated context and check for soft verification failures."""
    stage = (
        item.config.getoption("verifies_stage", default="default")
        or item.config.getini("verifies_stage")
        or "default"
    )
    is_soft = bool(
        item.config.getoption("verifies_soft", default=False) or item.config.getini("verifies_soft")
    )

    token_nodeid = _current_test_nodeid.set(item.nodeid)
    token_stage = _current_test_stage.set(stage)
    token_soft = _global_soft.set(is_soft)
    token_records = _active_records.set([])
    token_failures = _soft_failures.set([])

    try:
        outcome = yield
        if outcome.excinfo is None:
            failures = _soft_failures.get()
            if failures:
                summary = f"Soft verification failure(s) ({len(failures)}):\n" + "\n\n".join(
                    failures
                )
                pytest.fail(summary, pytrace=False)
    finally:
        item._verifies_harvested_records = list(_active_records.get())  # type: ignore[attr-defined]
        _current_test_nodeid.reset(token_nodeid)
        _current_test_stage.reset(token_stage)
        _global_soft.reset(token_soft)
        _active_records.reset(token_records)
        _soft_failures.reset(token_failures)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[Any],
) -> Generator[None, Any, pytest.TestReport]:
    """Construct report, harvest verified requirements, and inject user properties."""
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    is_setup_skip_or_fail = report.when == "setup" and (report.skipped or report.failed)
    if report.when != "call" and not is_setup_skip_or_fail:
        return report

    stage = (
        item.config.getoption("verifies_stage", default="default")
        or item.config.getini("verifies_stage")
        or "default"
    )

    # 1. Harvest block-level records recorded via with verifies(...)
    records: list[VerificationRecord] = list(getattr(item, "_verifies_harvested_records", []))
    evaluated_req_ids = {rid for r in records for rid in r.req_ids}

    # 2. Harvest marker-based requirements
    loc = (
        f"{item.location[0]}:{item.location[1] + 1}"
        if hasattr(item, "location") and item.location and item.location[1] is not None
        else item.nodeid
    )

    for marker in item.iter_markers(name="verifies"):
        marker_req_ids: list[str] = []
        for arg in marker.args:
            if isinstance(arg, str) and arg.strip():
                marker_req_ids.append(arg.strip())
            elif isinstance(arg, (list, tuple, set)):
                for sub in arg:
                    if isinstance(sub, str) and sub.strip():
                        marker_req_ids.append(sub.strip())

        desc = marker.kwargs.get("description")
        ev = marker.kwargs.get("evidence")
        step_id = marker.kwargs.get("step_id") or marker.kwargs.get("step")

        if hasattr(report, "wasxfail"):
            if report.skipped:
                m_status = "XFAILED"
            elif report.passed:
                m_status = "XPASS"
            else:
                m_status = "FAILED"
        elif report.passed:
            m_status = "PASSED"
        elif report.failed:
            m_status = "FAILED"
        elif report.skipped:
            m_status = "SKIPPED"
        else:
            m_status = "ERROR"

        msg = None
        if m_status in ("FAILED", "ERROR", "XFAILED"):
            msg = getattr(report, "longreprtext", None) or (
                str(report.longrepr) if report.longrepr else None
            )

        if not marker_req_ids and step_id:
            m_record = VerificationRecord(
                nodeid=item.nodeid,
                req_ids=[],
                status=m_status,
                stage=stage,
                step_id=step_id,
                location=loc,
                description=desc,
                message=msg,
                evidence=ev,
                duration_s=getattr(report, "duration", 0.0),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            records.append(m_record)

        for req_id in marker_req_ids:
            if report.passed and req_id in evaluated_req_ids:
                continue

            m_record = VerificationRecord(
                nodeid=item.nodeid,
                req_ids=[req_id],
                status=m_status,
                stage=stage,
                step_id=step_id,
                location=loc,
                description=desc,
                message=msg,
                evidence=ev,
                duration_s=getattr(report, "duration", 0.0),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            records.append(m_record)
            evaluated_req_ids.add(req_id)

    # 3. JUnit XML & xdist property injection
    user_props: list[tuple[str, Any]] = [("verifies_records", [r.to_dict() for r in records])]
    unique_req_ids = sorted({rid for r in records for rid in r.req_ids})
    for req_id in unique_req_ids:
        user_props.append(("verifies", req_id))

    report.user_properties.extend(user_props)
    if hasattr(item, "user_properties"):
        item.user_properties.extend(user_props)

    return report
