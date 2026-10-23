"""Domain models and data structures for requirements traceability.

All data structures are serialisable to JSON and provide full type annotations.
Consistent British English spelling is used throughout.
"""

from __future__ import annotations

import collections.abc
from dataclasses import dataclass, field
from typing import Any


def _normalise_json(value: Any) -> Any:
    """Recursively convert arbitrary Python values into JSON- and xdist-safe primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _normalise_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise_json(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_normalise_json(v) for v in sorted(value, key=str)]
    return str(value)


@dataclass
class BaselineRequirement:
    """Represents a requirement definition imported from an external baseline manifest."""

    id: str
    text: str = ""

    def __post_init__(self) -> None:
        self.id = self.id.strip()
        self.text = self.text.strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialise baseline requirement to a dictionary."""
        return {
            "id": self.id,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRequirement:
        """Deserialise baseline requirement from a dictionary."""
        raw_text = ""
        for key in ("text", "description", "title", "requirement"):
            val = data.get(key)
            if val is not None and str(val).strip():
                raw_text = str(val).strip()
                break
        return cls(
            id=str(data.get("id") or "").strip(),
            text=raw_text,
        )


@dataclass
class VerificationRecord:
    """Represents an atomic verification result or test procedure step."""

    nodeid: str
    req_ids: list[str]
    status: str  # "PASSED", "FAILED", "ERROR", "SKIPPED", "XFAILED", "XPASS"
    stage: str = "default"
    step_id: str | None = None
    location: str = ""
    description: str | None = None
    message: str | None = None
    evidence: Any = None
    duration_s: float = 0.0
    timestamp: str = ""

    def __post_init__(self) -> None:
        self.req_ids = [s for r in self.req_ids if r is not None and (s := str(r).strip())]
        self.evidence = _normalise_json(self.evidence)

    @property
    def is_action(self) -> bool:
        """Return True if this record represents an action step without requirement IDs."""
        return bool(self.step_id is not None and not self.req_ids)

    def to_dict(self) -> dict[str, Any]:
        """Serialise verification record to a JSON-compatible dictionary."""
        return {
            "nodeid": self.nodeid,
            "req_ids": list(self.req_ids),
            "status": self.status,
            "stage": self.stage,
            "step_id": self.step_id,
            "location": self.location,
            "description": self.description,
            "message": self.message,
            "evidence": _normalise_json(self.evidence),
            "duration_s": round(self.duration_s, 6),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationRecord:
        """Deserialise verification record from a dictionary."""
        raw_reqs = data.get("req_ids") or []
        if isinstance(raw_reqs, str):
            raw_reqs = [raw_reqs]
        elif not isinstance(raw_reqs, collections.abc.Iterable):
            raw_reqs = []
        raw_step = data.get("step_id")
        step_id = str(raw_step).strip() if raw_step is not None and str(raw_step).strip() else None
        raw_desc = data.get("description")
        description = str(raw_desc) if raw_desc is not None else None
        raw_msg = data.get("message")
        message = str(raw_msg) if raw_msg is not None else None
        raw_stage = data.get("stage")
        stage = (str(raw_stage).strip() if raw_stage is not None else "") or "default"
        return cls(
            nodeid=str(data.get("nodeid") or ""),
            req_ids=[s for r in raw_reqs if r is not None and (s := str(r).strip())],
            status=str(data.get("status") or "UNVERIFIED"),
            stage=stage,
            step_id=step_id,
            location=str(data.get("location") or ""),
            description=description,
            message=message,
            evidence=_normalise_json(data.get("evidence")),
            duration_s=float(data.get("duration_s") or 0.0),
            timestamp=str(data.get("timestamp") or ""),
        )


@dataclass
class ConsolidatedRequirement:
    """Consolidated traceability status and evidence for an individual requirement."""

    req_id: str
    text: str = ""
    in_baseline: bool = True
    is_orphan: bool = False
    status: str = "UNVERIFIED"  # "VERIFIED", "FAILED", "UNVERIFIED"
    stages_verified: dict[str, str] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    records: list[VerificationRecord] = field(default_factory=list)
    verified_by_tests: list[str] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    failure_messages: list[str] = field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        """Return True if the requirement is verified but has unverified stages or skipped records."""
        return self.status == "VERIFIED" and (
            any(s == "UNVERIFIED" for s in self.stages_verified.values())
            or any(r.status == "SKIPPED" for r in self.records)
        )

    @property
    def display_status(self) -> str:
        """Return human-readable status ('FAILED', 'PARTIAL', 'VERIFIED', or 'UNVERIFIED')."""
        if self.status == "FAILED":
            return "FAILED"
        if self.status == "VERIFIED":
            return "PARTIAL" if self.is_partial else "VERIFIED"
        return "UNVERIFIED"

    def to_dict(self) -> dict[str, Any]:
        """Serialise consolidated requirement to a dictionary."""
        return {
            "req_id": self.req_id,
            "text": self.text,
            "in_baseline": self.in_baseline,
            "is_orphan": self.is_orphan,
            "status": self.status,
            "stages_verified": dict(self.stages_verified),
            "steps": list(self.steps),
            "records": [r.to_dict() for r in self.records],
            "verified_by_tests": list(self.verified_by_tests),
            "evidence": [_normalise_json(e) for e in self.evidence],
            "failure_messages": list(self.failure_messages),
        }


@dataclass
class RTMReport:
    """Top-level Requirements Traceability Matrix report holding aggregated metrics."""

    title: str = "Requirements Traceability Matrix"
    generated_at: str = ""
    total_baseline_requirements: int = 0
    total_observed_requirements: int = 0
    verified_count: int = 0
    failed_count: int = 0
    unverified_count: int = 0
    orphan_count: int = 0
    coverage_percentage: float = 0.0
    requirements: list[ConsolidatedRequirement] = field(default_factory=list)
    test_records: list[VerificationRecord] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def partial_count(self) -> int:
        """Return the number of verified requirements with partial verification."""
        return sum(1 for r in self.requirements if r.is_partial)

    def to_dict(self) -> dict[str, Any]:
        """Serialise complete RTM report to a dictionary."""
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "summary": {
                "total_baseline_requirements": self.total_baseline_requirements,
                "total_observed_requirements": self.total_observed_requirements,
                "verified_count": self.verified_count,
                "failed_count": self.failed_count,
                "unverified_count": self.unverified_count,
                "orphan_count": self.orphan_count,
                "coverage_percentage": round(self.coverage_percentage, 2),
            },
            "requirements": [r.to_dict() for r in self.requirements],
            "test_records": [r.to_dict() for r in self.test_records],
            "runs": list(self.runs),
        }
