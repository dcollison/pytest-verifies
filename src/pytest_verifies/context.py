"""Execution context management and unified verifies decorator/context manager.

Provides the `verifies` callable which operates seamlessly as both a test decorator
(wrapping pytest.mark.verifies) and a context manager supporting soft assertions,
caller location capture, and dynamic objective evidence attachment.
"""

from __future__ import annotations

import collections.abc
import inspect
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable

import pytest

try:
    from _pytest.outcomes import Skipped, XFailed
except ImportError:  # pragma: no cover
    Skipped = ()  # type: ignore[assignment, misc]
    XFailed = ()  # type: ignore[assignment, misc]

from pytest_verifies.models import VerificationRecord

# Context variables for isolating state across async/threaded/synchronous test execution
_current_test_nodeid: ContextVar[str | None] = ContextVar("_current_test_nodeid", default=None)
_current_test_stage: ContextVar[str] = ContextVar("_current_test_stage", default="default")
_active_records: ContextVar[list[VerificationRecord]] = ContextVar("_active_records")
_soft_failures: ContextVar[list[str]] = ContextVar("_soft_failures")
_global_soft: ContextVar[bool] = ContextVar("_global_soft", default=False)


class _VerifiesContext(collections.abc.Collection):
    """Unified handler operating as both a pytest decorator and a context manager."""

    def __init__(
        self,
        *req_ids: str | Iterable[str],
        description: str | None = None,
        soft: bool = False,
        evidence: Any = None,
    ) -> None:
        """Initialise verification context with requirement identifiers and optional metadata."""
        flattened: list[str] = []
        for item in req_ids:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    flattened.append(cleaned)
            elif isinstance(item, collections.abc.Iterable):
                for sub in item:
                    if isinstance(sub, str) and sub.strip():
                        flattened.append(sub.strip())

        if not flattened:
            raise ValueError("At least one non-empty requirement ID must be specified.")

        self.req_ids: tuple[str, ...] = tuple(flattened)
        self.description: str | None = description
        self.soft: bool = soft
        self.evidence: Any = evidence
        self.location: str = ""
        self._start_time: float = 0.0

    @property
    def mark_decorator(self) -> pytest.MarkDecorator:
        """Pytest MarkDecorator representing this verification marker."""
        return pytest.mark.verifies(  # type: ignore[no-any-return]
            *self.req_ids,
            description=self.description,
            evidence=self.evidence,
        )

    @property
    def mark(self) -> pytest.Mark:
        """Underlying pytest Mark instance."""
        return self.mark_decorator.mark  # type: ignore[no-any-return]

    @property
    def name(self) -> str:
        """Marker name recognised by pytest."""
        return "verifies"

    def attach(self, key: str, value: Any) -> _VerifiesContext:
        """Attach a single key-value evidence entry dynamically during execution."""
        if self.evidence is None:
            self.evidence = {key: value}
        elif isinstance(self.evidence, dict):
            self.evidence[key] = value
        else:
            self.evidence = {"original_evidence": self.evidence, key: value}
        return self

    def record_evidence(self, data: Any) -> _VerifiesContext:
        """Record or merge structured objective evidence during execution."""
        if isinstance(data, dict) and isinstance(self.evidence, dict):
            self.evidence.update(data)
        elif self.evidence is None:
            self.evidence = data
        else:
            self.evidence = data
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

        if exc_type is None:
            status = "PASSED"
        elif issubclass(exc_type, AssertionError):
            status = "FAILED"
            message = str(exc_val).strip() if exc_val is not None else "AssertionError"
        elif (isinstance(Skipped, type) and issubclass(exc_type, Skipped)) or (
            hasattr(pytest, "skip")
            and hasattr(pytest.skip, "Exception")
            and issubclass(exc_type, pytest.skip.Exception)
        ):
            status = "SKIPPED"
            message = str(exc_val).strip() if exc_val is not None else None
        elif (isinstance(XFailed, type) and issubclass(exc_type, XFailed)) or (
            hasattr(pytest, "xfail")
            and hasattr(pytest.xfail, "Exception")
            and issubclass(exc_type, pytest.xfail.Exception)
        ):
            status = "XFAILED"
            message = str(exc_val).strip() if exc_val is not None else None
        else:
            status = "ERROR"
            message = str(exc_val).strip() if exc_val is not None else exc_type.__name__

        nodeid = _current_test_nodeid.get() or "unknown"
        stage = _current_test_stage.get()

        record = VerificationRecord(
            nodeid=nodeid,
            req_ids=list(self.req_ids),
            status=status,
            stage=stage,
            location=self.location,
            description=self.description,
            message=message,
            evidence=self.evidence,
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
            formatted_exc = str(exc_val).strip() if exc_val is not None else "AssertionError"
            failure_entry = f"[{', '.join(self.req_ids)}] ({self.location}):\n{formatted_exc}"
            try:
                soft_list = _soft_failures.get()
                soft_list.append(failure_entry)
            except LookupError:
                pass
            return True  # Suppress AssertionError to allow subsequent checks to execute

        return False


def verifies(
    *req_ids: str | Iterable[str],
    description: str | None = None,
    soft: bool = False,
    evidence: Any = None,
) -> _VerifiesContext:
    """Enterprise requirements traceability callable acting as both decorator and context manager.

    Args:
        *req_ids: One or more requirement identifiers (e.g. "REQ-001", "REQ-002").
        description: Optional human-readable requirement description.
        soft: If True, assertion failures are logged without terminating the test function.
        evidence: Optional arbitrary data (dict, string, etc.) representing verification evidence.

    Returns:
        _VerifiesContext: Unified instance supporting decorator and context manager protocols.
    """
    return _VerifiesContext(
        *req_ids,
        description=description,
        soft=soft,
        evidence=evidence,
    )
