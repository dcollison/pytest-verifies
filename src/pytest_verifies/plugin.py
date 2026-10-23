"""Pytest plugin hooks for requirements traceability.

Implements CLI options, collection filtering, AST analysis, execution recording,
xdist-safe property transmission, shard persistence, and quality gate evaluations.
"""

from __future__ import annotations

import ast
import fnmatch
import inspect
import textwrap
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

import pytest

from pytest_verifies.baseline import load_baseline
from pytest_verifies.context import (
    _active_records,
    _current_test_nodeid,
    _current_test_stage,
    _global_soft,
    _has_action_soft_failure,
    _last_unhandled_req_exc,
    _soft_failures,
    flatten_req_ids,
)
from pytest_verifies.models import BaselineRequirement, RTMReport, VerificationRecord
from pytest_verifies.reporters import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
    render_console_summary,
)
from pytest_verifies.storage import consolidate_requirements, write_shard


def _get_stage(config: pytest.Config) -> str:
    """Resolve the active execution stage from CLI option or ini configuration."""
    stage = config.getoption("verifies_stage") or config.getini("verifies_stage") or "default"
    return str(stage).strip() or "default"


def _get_soft(config: pytest.Config) -> bool:
    """Resolve whether global soft assertion mode is enabled."""
    return bool(config.getoption("verifies_soft", default=False) or config.getini("verifies_soft"))


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
        default=None,
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


def _extract_ast_strings(node: ast.AST) -> set[str]:
    """Extract non-empty string literals from an AST Constant or collection node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        val = node.value.strip()
        return {val} if val else set()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        result: set[str] = set()
        for elt in node.elts:
            result.update(_extract_ast_strings(elt))
        return result
    return set()


def extract_requirements_from_item(item: pytest.Item) -> set[str]:
    """Extract linked requirement IDs from item markers and AST inspection of function body."""
    extracted: set[str] = set()

    # 1. Markers (captures @verifies(...) and pytest.param(..., marks=verifies(...)))
    for marker in item.iter_markers(name="verifies"):
        extracted.update(
            flatten_req_ids(
                *marker.args,
                marker.kwargs.get("verifies"),
                marker.kwargs.get("req_ids"),
                marker.kwargs.get("req_id"),
            )
        )

    # 2. Fast AST inspection of item.obj
    fn = getattr(item, "obj", None)
    if fn is not None and callable(fn):
        try:
            source = inspect.getsource(fn)
            tree = ast.parse(textwrap.dedent(source))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.With, ast.AsyncWith)):
                    continue
                for with_item in node.items:
                    expr = with_item.context_expr
                    if not isinstance(expr, ast.Call):
                        continue
                    func_name = (
                        expr.func.id
                        if isinstance(expr.func, ast.Name)
                        else expr.func.attr
                        if isinstance(expr.func, ast.Attribute)
                        else None
                    )
                    if func_name == "verifies":
                        for arg in expr.args:
                            extracted.update(_extract_ast_strings(arg))
                    elif func_name == "step":
                        if len(expr.args) >= 2 and not (
                            isinstance(expr.args[1], ast.Constant)
                            and isinstance(expr.args[1].value, str)
                        ):
                            extracted.update(_extract_ast_strings(expr.args[1]))
                        for arg in expr.args[2:]:
                            extracted.update(_extract_ast_strings(arg))
                    else:
                        continue

                    for kw in expr.keywords:
                        if kw.arg in ("req_id", "req_ids", "verifies"):
                            extracted.update(_extract_ast_strings(kw.value))
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
        self.report: RTMReport | None = None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Harvest verification records from user_properties transmitted by worker or local run."""
        if hasattr(self.config, "workerinput"):
            return

        if report.when not in ("setup", "call", "teardown"):
            return

        for name, value in report.user_properties:
            if name == "verifies_records" and isinstance(value, list):
                for r_dict in value:
                    if isinstance(r_dict, dict):
                        self.buffer.append(VerificationRecord.from_dict(r_dict))

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Write execution shard and evaluate quality gates on the controller node."""
        if hasattr(session.config, "workerinput") or session.config.getoption("collectonly"):
            return

        # 1. Write execution shard if requested
        out_dir = session.config.getoption("verifies_out") or session.config.getini("verifies_out")
        stage = _get_stage(session.config)

        if out_dir:
            write_shard(
                output_dir=out_dir,
                stage=stage,
                records=self.buffer,
            )

        # 2. Check direct reporting flags and quality gate checks
        json_out = session.config.getoption("verifies_json")
        csv_out = session.config.getoption("verifies_csv")
        md_out = session.config.getoption("verifies_md")
        html_out = session.config.getoption("verifies_html")
        fail_under = session.config.getoption("verifies_fail_under")
        disallow_orphans = session.config.getoption("verifies_disallow_orphans")

        should_consolidate = bool(
            self.buffer
            or self.baseline_map
            or json_out
            or csv_out
            or md_out
            or html_out
            or (fail_under is not None)
            or disallow_orphans
        )

        if should_consolidate:
            report = consolidate_requirements(self.buffer, baseline=self.baseline_map)
            self.report = report

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

            # Gate A: Any requirement with test failures (FAIL or PARTIAL with failure)
            if any(r.has_failure for r in report.requirements):
                gate_failed = True

            # Gate B: Disallow orphans
            if disallow_orphans and report.orphan_count > 0:
                gate_failed = True

            # Gate C: Coverage threshold
            if fail_under is not None and report.coverage_percentage < fail_under:
                gate_failed = True

            if gate_failed and session.exitstatus in (
                pytest.ExitCode.OK,
                pytest.ExitCode.NO_TESTS_COLLECTED,
            ):
                session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(
        self,
        terminalreporter: Any,
        exitstatus: int,
        config: pytest.Config,
    ) -> None:
        """Render a clean, coloured console summary table respecting --color options."""
        if hasattr(self.config, "workerinput") or config.getoption("collectonly"):
            return

        # Do not print if no requirements were tracked or baselined
        if not self.buffer and not self.baseline_map:
            return

        report = self.report or consolidate_requirements(self.buffer, baseline=self.baseline_map)
        if not report.requirements:
            return

        render_console_summary(report, terminalreporter)


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


@contextmanager
def _ensure_test_context(item: pytest.Item) -> Iterator[None]:
    """Ensure context variables are initialised for the given test item."""
    if _current_test_nodeid.get() == item.nodeid:
        yield
        return

    token_nodeid = _current_test_nodeid.set(item.nodeid)
    token_stage = _current_test_stage.set(_get_stage(item.config))
    token_soft = _global_soft.set(_get_soft(item.config))
    token_records = _active_records.set([])
    token_failures = _soft_failures.set([])
    token_last_exc = _last_unhandled_req_exc.set(None)
    token_action_soft = _has_action_soft_failure.set(False)
    try:
        yield
    finally:
        _current_test_nodeid.reset(token_nodeid)
        _current_test_stage.reset(token_stage)
        _global_soft.reset(token_soft)
        _active_records.reset(token_records)
        _soft_failures.reset(token_failures)
        _last_unhandled_req_exc.reset(token_last_exc)
        _has_action_soft_failure.reset(token_action_soft)


def _run_phase_wrapper(item: pytest.Item) -> Generator[None, Any, None]:
    """Execute a test phase (setup, call, or teardown) and harvest records and soft failures."""
    with _ensure_test_context(item):
        _last_unhandled_req_exc.set(None)
        _has_action_soft_failure.set(False)
        item._verifies_phase_failed_by_req_block = False  # type: ignore[attr-defined]
        try:
            outcome = yield
            failures = list(_soft_failures.get())
            _soft_failures.get().clear()
            if outcome.excinfo is not None:
                last_req_exc = _last_unhandled_req_exc.get()
                item._verifies_phase_failed_by_req_block = (  # type: ignore[attr-defined]
                    last_req_exc is not None and outcome.excinfo[1] is last_req_exc
                )
            elif failures:
                item._verifies_phase_failed_by_req_block = not _has_action_soft_failure.get()  # type: ignore[attr-defined]
                summary = f"Soft verification failure(s) ({len(failures)}):\n" + "\n\n".join(
                    failures
                )
                pytest.fail(summary, pytrace=False)
        finally:
            _soft_failures.get().clear()
            _last_unhandled_req_exc.set(None)
            _has_action_soft_failure.set(False)
            harvested = list(_active_records.get())
            _active_records.get().clear()
            item._verifies_harvested_records = harvested  # type: ignore[attr-defined]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item,
    nextitem: pytest.Item | None,
) -> Generator[None, Any, None]:
    """Manage verification context variables across the entire test protocol (setup, call, teardown)."""
    item._verifies_harvested_records = []  # type: ignore[attr-defined]
    item._verifies_evaluated_req_ids = set()  # type: ignore[attr-defined]
    item._verifies_failed_req_ids = set()  # type: ignore[attr-defined]
    item._verifies_phase_failed_by_req_block = False  # type: ignore[attr-defined]
    with _ensure_test_context(item):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, Any, None]:
    """Execute test setup inside isolated context and check for soft verification failures."""
    yield from _run_phase_wrapper(item)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, None]:
    """Execute test call inside isolated context and check for soft verification failures."""
    yield from _run_phase_wrapper(item)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, Any, None]:
    """Execute test teardown inside isolated context and check for soft verification failures."""
    yield from _run_phase_wrapper(item)


def _resolve_report_status(report: pytest.TestReport) -> str:
    """Resolve verification record status from a pytest TestReport."""
    if hasattr(report, "wasxfail"):
        if report.skipped:
            return "XFAILED"
        if report.passed:
            return "XPASS"
        return "FAILED"
    if report.passed:
        return "PASSED"
    if report.failed:
        return "FAILED"
    if report.skipped:
        return "SKIPPED"
    return "ERROR"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[Any],
) -> Generator[None, Any, pytest.TestReport]:
    """Construct report, harvest verified requirements, and inject user properties."""
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    # 1. Harvest block-level records recorded via with verifies(...) / with step(...)
    records: list[VerificationRecord] = list(getattr(item, "_verifies_harvested_records", []))
    item._verifies_harvested_records = []  # type: ignore[attr-defined]

    is_setup_active = report.when == "setup" and (report.failed or report.skipped or bool(records))
    is_call_active = report.when == "call"
    is_teardown_active = report.when == "teardown" and (
        report.failed or report.skipped or bool(records)
    )
    if not (is_setup_active or is_call_active or is_teardown_active):
        return report

    stage = _get_stage(item.config)
    m_status = _resolve_report_status(report)
    is_phase_failure = m_status in ("FAILED", "ERROR", "XFAILED")
    msg: str | None = None
    if is_phase_failure:
        msg = getattr(report, "longreprtext", None) or (
            str(report.longrepr) if report.longrepr else None
        )
        if not msg and hasattr(report, "wasxfail"):
            msg = f"xfail: {report.wasxfail}" if report.wasxfail else "XFailed"

    # Downgrade block PASSED records if test failed due to strict xfail ([XPASS(strict)])
    if (
        report.when == "call"
        and report.failed
        and (call.excinfo is None or hasattr(report, "wasxfail"))
    ):
        for r in records:
            if r.status in ("PASSED", "XPASS"):
                r.status = "FAILED"
                if not r.message and msg:
                    r.message = msg

    item_evaluated_req_ids: set[str] = getattr(item, "_verifies_evaluated_req_ids", set())
    item_failed_req_ids: set[str] = getattr(item, "_verifies_failed_req_ids", set())

    phase_evaluated_req_ids = {rid for r in records for rid in r.req_ids}
    phase_failed_req_ids = {
        rid for r in records if r.status in ("FAILED", "ERROR", "XFAILED") for rid in r.req_ids
    }
    item_evaluated_req_ids.update(phase_evaluated_req_ids)
    item_failed_req_ids.update(phase_failed_req_ids)

    failure_from_req_block = bool(
        getattr(item, "_verifies_phase_failed_by_req_block", False)
    ) and bool(phase_failed_req_ids)

    loc = (
        f"{Path(item.location[0]).as_posix()}:{item.location[1] + 1}"
        if hasattr(item, "location") and item.location and item.location[1] is not None
        else item.nodeid
    )

    # 2. Harvest marker-based requirements when appropriate for the phase
    should_evaluate_markers = (report.when == "call") or (
        report.when in ("setup", "teardown") and (is_phase_failure or m_status == "SKIPPED")
    )

    if should_evaluate_markers:
        for marker in item.iter_markers(name="verifies"):
            marker_req_ids = flatten_req_ids(
                *marker.args,
                marker.kwargs.get("verifies"),
                marker.kwargs.get("req_ids"),
                marker.kwargs.get("req_id"),
            )
            desc = marker.kwargs.get("description")
            ev = marker.kwargs.get("evidence")
            step_id = marker.kwargs.get("step_id") or marker.kwargs.get("step")

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
                if req_id in item_failed_req_ids:
                    continue
                if req_id in item_evaluated_req_ids and (
                    not is_phase_failure or failure_from_req_block
                ):
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
                item_evaluated_req_ids.add(req_id)
                if is_phase_failure:
                    item_failed_req_ids.add(req_id)

        # If a phase failed outside any requirement block, invalidate requirements evaluated in this phase (or setup/call on teardown)
        if is_phase_failure and not failure_from_req_block:
            candidate_reqs = (
                item_evaluated_req_ids if report.when == "teardown" else phase_evaluated_req_ids
            )
            for req_id in sorted(candidate_reqs - item_failed_req_ids):
                records.append(
                    VerificationRecord(
                        nodeid=item.nodeid,
                        req_ids=[req_id],
                        status=m_status,
                        stage=stage,
                        location=loc,
                        message=msg,
                        duration_s=getattr(report, "duration", 0.0),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                item_failed_req_ids.add(req_id)

    item._verifies_evaluated_req_ids = item_evaluated_req_ids  # type: ignore[attr-defined]
    item._verifies_failed_req_ids = item_failed_req_ids  # type: ignore[attr-defined]

    # 3. JUnit XML & xdist property injection
    if records:
        report.user_properties.append(("verifies_records", [r.to_dict() for r in records]))
    unique_req_ids = sorted({rid for r in records for rid in r.req_ids})
    for req_id in unique_req_ids:
        prop = ("verifies", req_id)
        if prop not in report.user_properties:
            report.user_properties.append(prop)
        if hasattr(item, "user_properties") and prop not in item.user_properties:
            item.user_properties.append(prop)

    return report
