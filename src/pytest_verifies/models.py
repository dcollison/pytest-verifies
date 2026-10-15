"""Domain models and data structures for requirements traceability.

All data structures are serialisable to JSON and provide full type annotations.
Consistent British English spelling is used throughout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BaselineRequirement:
    """Represents a requirement definition imported from an external baseline manifest."""

    id: str
    title: str = ""
    description: str = ""
    priority: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise baseline requirement to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRequirement:
        """Deserialise baseline requirement from a dictionary."""
        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            description=str(data.get("description", "")).strip(),
            priority=str(data.get("priority", "")).strip(),
            category=str(data.get("category", "")).strip(),
        )


@dataclass
class VerificationRecord:
    """Represents an atomic verification result for one or more requirements."""

    nodeid: str
    req_ids: list[str]
    status: str  # "PASSED", "FAILED", "ERROR", "SKIPPED", "XFAILED", "XPASS"
    stage: str = "default"
    location: str = ""
    description: str | None = None
    message: str | None = None
    evidence: Any = None
    duration_s: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise verification record to a JSON-compatible dictionary."""
        return {
            "nodeid": self.nodeid,
            "req_ids": list(self.req_ids),
            "status": self.status,
            "stage": self.stage,
            "location": self.location,
            "description": self.description,
            "message": self.message,
            "evidence": self.evidence,
            "duration_s": round(self.duration_s, 6),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationRecord:
        """Deserialise verification record from a dictionary."""
        return cls(
            nodeid=str(data.get("nodeid", "")),
            req_ids=[str(r) for r in data.get("req_ids", [])],
            status=str(data.get("status", "UNVERIFIED")),
            stage=str(data.get("stage", "default")),
            location=str(data.get("location", "")),
            description=data.get("description"),
            message=data.get("message"),
            evidence=data.get("evidence"),
            duration_s=float(data.get("duration_s", 0.0)),
            timestamp=str(data.get("timestamp", "")),
        )


@dataclass
class TestExecutionRecord:
    """Metadata and execution context for a single test shard run."""

    run_id: str
    stage: str
    timestamp: str
    git_sha: str | None = None
    git_dirty: bool | None = None
    python_version: str = ""
    pytest_version: str = ""
    hostname: str = ""
    records: list[VerificationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise test execution run metadata to a dictionary."""
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "git_dirty": self.git_dirty,
            "python_version": self.python_version,
            "pytest_version": self.pytest_version,
            "hostname": self.hostname,
            "records": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestExecutionRecord:
        """Deserialise test execution run metadata from a dictionary."""
        records_raw = data.get("records", [])
        return cls(
            run_id=str(data.get("run_id", "")),
            stage=str(data.get("stage", "default")),
            timestamp=str(data.get("timestamp", "")),
            git_sha=data.get("git_sha"),
            git_dirty=data.get("git_dirty"),
            python_version=str(data.get("python_version", "")),
            pytest_version=str(data.get("pytest_version", "")),
            hostname=str(data.get("hostname", "")),
            records=[VerificationRecord.from_dict(r) for r in records_raw],
        )


@dataclass
class ConsolidatedRequirement:
    """Consolidated traceability status and evidence for an individual requirement."""

    req_id: str
    title: str = ""
    description: str = ""
    priority: str = ""
    in_baseline: bool = True
    is_orphan: bool = False
    status: str = "UNVERIFIED"  # "VERIFIED", "FAILED", "UNVERIFIED"
    stages_verified: dict[str, str] = field(default_factory=dict)
    records: list[VerificationRecord] = field(default_factory=list)
    verified_by_tests: list[str] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    failure_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise consolidated requirement to a dictionary."""
        return {
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "in_baseline": self.in_baseline,
            "is_orphan": self.is_orphan,
            "status": self.status,
            "stages_verified": dict(self.stages_verified),
            "records": [r.to_dict() for r in self.records],
            "verified_by_tests": list(self.verified_by_tests),
            "evidence": list(self.evidence),
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
    runs: list[dict[str, Any]] = field(default_factory=list)

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
            "runs": list(self.runs),
        }
