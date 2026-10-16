"""JSONL shard storage, multi-run aggregator, and status consolidation.

Handles writing atomic execution shards per test invocation and merging them across
different stages and parallel workers into a consolidated Requirements Traceability Matrix.
"""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from pytest_verifies.models import (
    BaselineRequirement,
    ConsolidatedRequirement,
    RTMReport,
    VerificationRecord,
)


def get_git_info() -> tuple[str | None, bool | None]:
    """Retrieve current Git commit SHA and dirty state if available."""
    sha: str | None = None
    dirty: bool | None = None
    try:
        res_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if res_sha.returncode == 0 and res_sha.stdout.strip():
            sha = res_sha.stdout.strip()

        res_dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if res_dirty.returncode == 0:
            dirty = bool(res_dirty.stdout.strip())
    except Exception:
        pass
    return sha, dirty


def write_shard(
    output_dir: str | Path,
    stage: str,
    records: list[VerificationRecord],
    run_id: str | None = None,
) -> Path:
    """Write an execution shard file in JSON Lines (.jsonl) format.

    Args:
        output_dir: Destination directory for shard files.
        stage: Test execution stage label (e.g. 'unit', 'integration', 'system').
        records: Collection of verification records captured during execution.
        run_id: Optional unique identifier for this run; generates a UUID if omitted.

    Returns:
        Path: Absolute path to the newly written shard file.
    """
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    actual_run_id = run_id or str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    timestamp_compact = now_utc.strftime("%Y%m%dT%H%M%SZ")
    uuid8 = actual_run_id.replace("-", "")[:8]
    filename = f"verifies.{stage}.{timestamp_compact}.{uuid8}.jsonl"
    file_path = dest_dir / filename

    git_sha, git_dirty = get_git_info()

    metadata: dict[str, Any] = {
        "type": "metadata",
        "run_id": actual_run_id,
        "stage": stage,
        "timestamp": now_utc.isoformat(),
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "python_version": platform.python_version(),
        "pytest_version": pytest.__version__,
        "hostname": socket.gethostname(),
    }

    with file_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(metadata) + "\n")
        for record in records:
            record_dict = record.to_dict()
            record_dict["type"] = "record"
            f.write(json.dumps(record_dict) + "\n")

    return file_path


def read_shards(
    paths: list[str | Path],
) -> tuple[list[dict[str, Any]], list[VerificationRecord]]:
    """Read and parse shard files from a list of files and directories.

    Args:
        paths: List of file or directory paths pointing to .jsonl shards.

    Returns:
        tuple[list[dict], list[VerificationRecord]]: Discovered run metadata list and all verification records.
    """
    discovered_files: list[Path] = []
    for p in paths:
        path_obj = Path(p)
        if path_obj.is_file():
            discovered_files.append(path_obj)
        elif path_obj.is_dir():
            discovered_files.extend(sorted(path_obj.glob("*.jsonl")))
            discovered_files.extend(sorted(path_obj.glob("**/*.jsonl")))

    # Deduplicate while preserving order
    unique_files: list[Path] = []
    seen: set[Path] = set()
    for f in discovered_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_files.append(f)

    runs: list[dict[str, Any]] = []
    records: list[VerificationRecord] = []

    for file_path in unique_files:
        try:
            with file_path.open("r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    entry_type = entry.get("type")
                    if entry_type == "metadata":
                        runs.append(entry)
                    elif entry_type == "record":
                        records.append(VerificationRecord.from_dict(entry))
        except OSError:
            continue

    return runs, records


def consolidate_requirements(
    records: list[VerificationRecord],
    baseline: dict[str, BaselineRequirement] | None = None,
    runs: list[dict[str, Any]] | None = None,
) -> RTMReport:
    """Consolidate raw verification records across runs/stages against an optional baseline.

    Applies deterministic status resolution:
      - FAILED: At least one record is FAILED, ERROR, or XFAILED.
      - VERIFIED: At least one record is PASSED or XPASS, and ZERO are FAILED, ERROR, or XFAILED.
      - UNVERIFIED: No records exist, or all records are SKIPPED.

    Args:
        records: Collection of verification records from one or more shards.
        baseline: Optional dictionary of baseline requirements.
        runs: Optional metadata dictionaries describing individual shard runs.

    Returns:
        RTMReport: Consolidated Requirements Traceability Matrix report.
    """
    # 1. Gather all unique requirement IDs
    observed_req_ids: set[str] = set()
    records_by_req: dict[str, list[VerificationRecord]] = {}

    for record in records:
        for req_id in record.req_ids:
            observed_req_ids.add(req_id)
            records_by_req.setdefault(req_id, []).append(record)

    baseline_req_ids = set(baseline.keys()) if baseline is not None else set()
    all_req_ids = sorted(baseline_req_ids | observed_req_ids)

    consolidated_list: list[ConsolidatedRequirement] = []
    verified_count = 0
    failed_count = 0
    unverified_count = 0
    orphan_count = 0

    for req_id in all_req_ids:
        in_baseline = baseline is not None and req_id in baseline
        is_orphan = baseline is not None and req_id not in baseline
        if is_orphan:
            orphan_count += 1

        req_baseline = baseline.get(req_id) if baseline else None
        title = req_baseline.title if req_baseline else ""
        description = req_baseline.description if req_baseline else ""
        priority = req_baseline.priority if req_baseline else ""

        req_records = records_by_req.get(req_id, [])

        # If description is missing from baseline, infer from record if available
        if not description:
            for r in req_records:
                if r.description:
                    description = r.description
                    break

        # 2. Determine consolidated status
        has_failure = any(r.status in ("FAILED", "ERROR", "XFAILED") for r in req_records)
        has_pass = any(r.status in ("PASSED", "XPASS") for r in req_records)

        if has_failure:
            status = "FAILED"
            failed_count += 1
        elif has_pass:
            status = "VERIFIED"
            verified_count += 1
        else:
            status = "UNVERIFIED"
            unverified_count += 1

        # 3. Stage breakdown
        stages_verified: dict[str, str] = {}
        stage_grouped: dict[str, list[VerificationRecord]] = {}
        for r in req_records:
            stage_grouped.setdefault(r.stage, []).append(r)

        for stage, s_records in sorted(stage_grouped.items()):
            s_fail = any(sr.status in ("FAILED", "ERROR", "XFAILED") for sr in s_records)
            s_pass = any(sr.status in ("PASSED", "XPASS") for sr in s_records)
            if s_fail:
                stages_verified[stage] = "FAILED"
            elif s_pass:
                stages_verified[stage] = "VERIFIED"
            else:
                stages_verified[stage] = "UNVERIFIED"

        # 4. Evidence and failure aggregation
        verified_by_tests: list[str] = sorted(
            {r.nodeid for r in req_records if r.status in ("PASSED", "XPASS")}
        )
        steps_list: list[str] = sorted({r.step_id for r in req_records if r.step_id})
        evidence_list: list[Any] = [r.evidence for r in req_records if r.evidence is not None]
        failure_messages: list[str] = [
            r.message
            for r in req_records
            if r.status in ("FAILED", "ERROR", "XFAILED") and r.message
        ]

        consolidated = ConsolidatedRequirement(
            req_id=req_id,
            title=title,
            description=description,
            priority=priority,
            in_baseline=in_baseline,
            is_orphan=is_orphan,
            status=status,
            stages_verified=stages_verified,
            steps=steps_list,
            records=req_records,
            verified_by_tests=verified_by_tests,
            evidence=evidence_list,
            failure_messages=failure_messages,
        )
        consolidated_list.append(consolidated)

    total_baseline = len(baseline) if baseline is not None else 0
    total_observed = len(observed_req_ids)

    if total_baseline > 0:
        coverage_percentage = (verified_count / total_baseline) * 100.0
    elif total_observed > 0:
        coverage_percentage = (verified_count / total_observed) * 100.0
    else:
        coverage_percentage = 0.0

    return RTMReport(
        title="Requirements Traceability Matrix",
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_baseline_requirements=total_baseline,
        total_observed_requirements=total_observed,
        verified_count=verified_count,
        failed_count=failed_count,
        unverified_count=unverified_count,
        orphan_count=orphan_count,
        coverage_percentage=coverage_percentage,
        requirements=consolidated_list,
        test_records=list(records),
        runs=runs or [],
    )
