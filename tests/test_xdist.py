"""Tests for pytest-xdist parallel worker execution and controller record aggregation."""

from __future__ import annotations

import json

import pytest


def test_xdist_parallel_execution_and_aggregation(pytester: pytest.Pytester) -> None:
    """Verify distributed workers transmit verification records safely to the controller node."""
    # Create test suite with 8 tests distributed across 2 workers
    tests_code = """
import time
from pathlib import Path
from pytest_verifies import verifies

@verifies("REQ-DIST-01")
def test_w1_01():
    time.sleep(0.01)
    assert True

@verifies("REQ-DIST-02")
def test_w1_02():
    time.sleep(0.01)
    assert True

def test_w2_03():
    with verifies("REQ-DIST-03", evidence={"worker_test": 3, "log": Path("/tmp/w3.log")}):
        assert True

def test_w2_04():
    with verifies("REQ-DIST-04", evidence={"worker_test": 4, "tags": {"xdist", "parallel"}}):
        assert True

@verifies("REQ-DIST-05")
def test_w1_05():
    assert True

@verifies("REQ-DIST-06")
def test_w2_06():
    assert True

def test_w1_07():
    with verifies("REQ-DIST-07"):
        assert True

def test_w2_08():
    with verifies("REQ-DIST-08"):
        assert True
"""
    pytester.makepyfile(tests_code)

    shards_dir = pytester.path / "shards"
    json_report = pytester.path / "xdist_rtm.json"

    result = pytester.runpytest(
        "-n",
        "2",
        f"--verifies-out={shards_dir}",
        f"--verifies-json={json_report}",
    )
    result.assert_outcomes(passed=8)

    # 1. Shards check
    assert shards_dir.is_dir()
    shard_files = list(shards_dir.glob("*.jsonl"))
    # The controller should have written exactly 1 shard for this run
    assert len(shard_files) == 1

    # Read shard and verify records count
    lines = shard_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 9  # 1 metadata line + 8 record lines
    metadata = json.loads(lines[0])
    assert metadata["type"] == "metadata"

    # 2. JSON Report check
    assert json_report.is_file()
    data = json.loads(json_report.read_text(encoding="utf-8"))

    reqs = {r["req_id"]: r for r in data["requirements"]}
    for i in range(1, 9):
        req_id = f"REQ-DIST-{i:02d}"
        assert req_id in reqs, f"Missing {req_id} from xdist aggregation"
        assert reqs[req_id]["status"] == "VERIFIED"

    assert data["summary"]["verified_count"] == 8
    assert data["summary"]["failed_count"] == 0
