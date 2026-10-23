"""Execution context management and unified verifies decorator/context manager.

Provides the `verifies` callable which operates seamlessly as both a test decorator
(wrapping pytest.mark.verifies) and a context manager supporting soft assertions,
caller location capture, and dynamic objective evidence attachment.
"""

from __future__ import annotations

import collections.abc
import copy
import inspect
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable

import pytest

from pytest_verifies.models import VerificationRecord

# Context variables for isolating state across async/threaded/synchronous test execution
_current_test_nodeid: ContextVar[str | None] = ContextVar("_current_test_nodeid", default=None)
_current_test_stage: ContextVar[str] = ContextVar("_current_test_stage", default="default")
_active_records: ContextVar[list[VerificationRecord]] = ContextVar("_active_records")
_soft_failures: ContextVar[list[str]] = ContextVar("_soft_failures")
_global_soft: ContextVar[bool] = ContextVar("_global_soft", default=False)
_last_unhandled_req_exc: ContextVar[BaseException | None] = ContextVar(
    "_last_unhandled_req_exc", default=None
)
_has_action_soft_failure: ContextVar[bool] = ContextVar("_has_action_soft_failure", default=False)


def flatten_req_ids(*items: Any) -> list[str]:
    """Flatten strings and iterables of strings into a list of non-empty requirement IDs."""
    flattened: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                flattened.append(cleaned)
        elif isinstance(item, collections.abc.Iterable):
            for sub in item:
                if isinstance(sub, str) and sub.strip():
                    flattened.append(sub.strip())
    return flattened


def _safe_deepcopy(value: Any) -> Any:
    """Deep-copy mutable structures, falling back to the original object if uncopyable."""
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


class _VerifiesContext(collections.abc.Collection[pytest.MarkDecorator]):
    """Unified handler operating as both a pytest decorator and a context manager."""

    def __init__(
        self,
        *req_ids: str | Iterable[str],
        step: str | None = None,
        step_id: str | None = None,
        description: str | None = None,
        soft: bool = False,
        evidence: Any = None,
    ) -> None:
        """Initialise verification context with requirement identifiers, step ID, and optional metadata."""
        flattened = flatten_req_ids(*req_ids)

        raw_step = step_id if step_id is not None else step
        cleaned_step = (
            str(raw_step).strip() if raw_step is not None and str(raw_step).strip() else None
        )

        if not flattened and cleaned_step is None:
            raise ValueError("At least one non-empty requirement ID or step ID must be specified.")

        self.req_ids: tuple[str, ...] = tuple(flattened)
        self.step_id: str | None = cleaned_step
        self.description: str | None = description
        self.soft: bool = soft
        self.evidence: Any = _safe_deepcopy(evidence)
        self._evidence_stack: list[Any] = []
        self.location: str = ""
        self._start_time: float = 0.0

    @property
    def step(self) -> str | None:
        """Return the current step identifier."""
        return self.step_id

    @step.setter
    def step(self, value: str | None) -> None:
        """Set the step identifier."""
        self.step_id = str(value).strip() if value is not None and str(value).strip() else None

    @property
    def mark_decorator(self) -> pytest.MarkDecorator:
        """Pytest MarkDecorator representing this verification marker."""
        return pytest.mark.verifies(
            *self.req_ids,
            step_id=self.step_id,
            description=self.description,
            evidence=_safe_deepcopy(self.evidence),
        )

    @property
    def mark(self) -> pytest.Mark:
        """Underlying pytest Mark instance."""
        return self.mark_decorator.mark

    @property
    def name(self) -> str:
        """Marker name recognised by pytest."""
        return "verifies"

    def attach(self, key: str, value: Any) -> _VerifiesContext:
        """Attach a single key-value evidence entry dynamically during execution."""
        copied_val = _safe_deepcopy(value)
        if self.evidence is None:
            self.evidence = {key: copied_val}
        elif isinstance(self.evidence, dict):
            self.evidence[key] = copied_val
        else:
            self.evidence = {"original_evidence": self.evidence, key: copied_val}
        return self

    def record_evidence(self, data: Any) -> _VerifiesContext:
        """Record or merge structured objective evidence during execution."""
        copied = _safe_deepcopy(data)
        if isinstance(copied, dict) and isinstance(self.evidence, dict):
            self.evidence.update(copied)
        else:
            self.evidence = copied
        return self

    # Decorator & collections.abc.Collection implementation for pytest.param compatibility
    def __call__(self, target: Any) -> Any:
        """Decorate a test function or test class with the verifies marker."""
        return self.mark_decorator(target)

    def __iter__(self) -> Generator[pytest.MarkDecorator, None, None]:
        """Yield the underlying MarkDecorator when enumerated in pytest.param(..., marks=...)."""
        yield self.mark_decorator

    def __len__(self) -> int:
        """Return collection length (always 1 for a single marker)."""
        return 1

    def __contains__(self, item: Any) -> bool:
        """Check marker membership."""
        return bool(item == self.mark_decorator or item == self.mark)

    # Context manager implementation
    def __enter__(self) -> _VerifiesContext:
        """Enter verification block, validating test context and capturing caller location."""
        nodeid = _current_test_nodeid.get()
        if nodeid is None:
            raise RuntimeError(
                "The 'verifies' context manager can only be used within an active pytest test context."
            )

        self._evidence_stack.append(_safe_deepcopy(self.evidence))
        self.evidence = _safe_deepcopy(self.evidence)

        # Inspect caller frame to capture source location
        frame = inspect.currentframe()
        caller_frame = frame.f_back if frame else None
        if caller_frame:
            filename = caller_frame.f_code.co_filename
            lineno = caller_frame.f_lineno
            try:
                relpath = Path(filename).relative_to(Path.cwd()).as_posix()
            except (ValueError, Exception):
                relpath = Path(filename).name
            self.location = f"{relpath}:{lineno}"
        else:
            self.location = "unknown:0"

        self._start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Exit verification block, evaluate assertion outcome, and record verification status."""
        duration = max(0.0, time.perf_counter() - self._start_time)
        status: str
        message: str | None = None
        raw_msg = str(exc_val).strip() if exc_val is not None else ""

        if exc_type is None:
            status = "PASSED"
        elif issubclass(exc_type, AssertionError):
            status = "FAILED"
            message = raw_msg or "AssertionError"
        elif issubclass(exc_type, pytest.skip.Exception):
            status = "SKIPPED"
            message = raw_msg or None
        elif issubclass(exc_type, pytest.xfail.Exception):
            status = "XFAILED"
            message = raw_msg or "XFailed"
        else:
            status = "ERROR"
            message = raw_msg or exc_type.__name__

        nodeid = _current_test_nodeid.get() or "unknown"
        stage = _current_test_stage.get()
        recorded_evidence = _safe_deepcopy(self.evidence)
        if self._evidence_stack:
            self.evidence = self._evidence_stack.pop()

        record = VerificationRecord(
            nodeid=nodeid,
            req_ids=list(self.req_ids),
            status=status,
            stage=stage,
            step_id=self.step_id,
            location=self.location,
            description=self.description,
            message=message,
            evidence=recorded_evidence,
            duration_s=duration,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        try:
            active = _active_records.get()
            active.append(record)
        except LookupError:
            pass

        # Handle soft assertion suppression
        is_soft = self.soft or _global_soft.get()
        if is_soft and exc_type is not None and issubclass(exc_type, AssertionError):
            formatted_exc = message or "AssertionError"
            step_tag = f" [Step: {self.step_id}]" if self.step_id else ""
            req_tag = f"[{', '.join(self.req_ids)}]" if self.req_ids else "[ACTION]"
            failure_entry = f"{req_tag}{step_tag} ({self.location}):\n{formatted_exc}"
            if not self.req_ids:
                _has_action_soft_failure.set(True)
            try:
                soft_list = _soft_failures.get()
                soft_list.append(failure_entry)
            except LookupError:
                pass
            return True  # Suppress AssertionError to allow subsequent checks to execute

        if exc_val is not None and self.req_ids:
            _last_unhandled_req_exc.set(exc_val)

        return False


def verifies(
    *req_ids: str | Iterable[str],
    step: str | None = None,
    step_id: str | None = None,
    description: str | None = None,
    soft: bool = False,
    evidence: Any = None,
) -> _VerifiesContext:
    """Enterprise requirements traceability callable acting as both decorator and context manager.

    Args:
        *req_ids: One or more requirement identifiers (e.g. "REQ-001", "REQ-002").
        step: Optional step identifier (e.g. "STEP-01").
        step_id: Alias for step.
        description: Optional human-readable requirement description.
        soft: If True, assertion failures are logged without terminating the test function.
        evidence: Optional arbitrary data (dict, string, etc.) representing verification evidence.

    Returns:
        _VerifiesContext: Unified instance supporting decorator and context manager protocols.
    """
    return _VerifiesContext(
        *req_ids,
        step=step,
        step_id=step_id,
        description=description,
        soft=soft,
        evidence=evidence,
    )


def step(
    step_id: str,
    description: str | Iterable[str] | None = None,
    *req_ids: str | Iterable[str],
    verifies: str | Iterable[str] | None = None,
    soft: bool = False,
    evidence: Any = None,
) -> _VerifiesContext:
    """Record a test procedure step (action step or requirement verification step).

    Args:
        step_id: Unique step identifier (e.g. "STEP-01", "STEP-1.2").
        description: Optional human-readable action or check description, or iterable of requirement IDs.
        *req_ids: Optional requirement identifiers verified by this step.
        verifies: Optional requirement identifier or collection of identifiers.
        soft: If True, assertion failures are logged without terminating the test.
        evidence: Optional arbitrary data (dict, string, etc.) representing step evidence.

    Returns:
        _VerifiesContext: Step context manager and decorator.
    """
    actual_desc: str | None
    extra_reqs: list[str | Iterable[str]] = []
    if description is not None and not isinstance(description, str):
        actual_desc = None
        extra_reqs.append(description)
    else:
        actual_desc = description

    return _VerifiesContext(
        *extra_reqs,
        *req_ids,
        *([] if verifies is None else [verifies]),
        step_id=step_id,
        description=actual_desc,
        soft=soft,
        evidence=evidence,
    )
