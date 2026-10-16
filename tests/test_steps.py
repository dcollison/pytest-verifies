"""Tests for test procedure step IDs and action steps in pytest-verifies."""

from __future__ import annotations

import json
from typing import Any

import pytest


def test_step_action_and_verification_context(pytester: pytest.Pytester) -> None:
    """Verify action steps and verification steps execute and record step IDs."""
    pytester.makepyfile(
        """
        from pytest_verifies import step, verifies

        def test_mixed_steps():
            # 1. Action step: Setup stimulus
            with step("STEP-01", description="Power on device") as s1:
                s1.attach("device_ready", True)
                status = "ready"
                assert status == "ready"

            # 2. Verification step using step(..., verifies=...)
            with step("STEP-02", description="Check nominal voltage", verifies="REQ-PWR-001"):
                assert 5.0 == 5.0

            # 3. Verification step using verifies(..., step=...)
            with verifies("REQ-PWR-002", step="STEP-03", description="Check current ripple"):
                assert 0.05 < 0.1
        """
    )

    out_dir = pytester.path / ".verifies"
    result = pytester.runpytest(f"--verifies-out={out_dir}", "--verifies-stage=unit")
    result.assert_outcomes(passed=1)

    # Check generated shard
    shard_files = list(out_dir.glob("*.jsonl"))
    assert len(shard_files) == 1

    records: list[dict[str, Any]] = []
    with shard_files[0].open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("type") == "record":
                records.append(data)

    assert len(records) == 3

    # Record 1: Action step
    assert records[0]["step_id"] == "STEP-01"
    assert records[0]["req_ids"] == []
    assert records[0]["status"] == "PASSED"
    assert records[0]["description"] == "Power on device"
    assert records[0]["evidence"] == {"device_ready": True}

    # Record 2: Verification step via step(...)
    assert records[1]["step_id"] == "STEP-02"
    assert records[1]["req_ids"] == ["REQ-PWR-001"]
    assert records[1]["status"] == "PASSED"

    # Record 3: Verification step via verifies(...)
    assert records[2]["step_id"] == "STEP-03"
    assert records[2]["req_ids"] == ["REQ-PWR-002"]
    assert records[2]["status"] == "PASSED"


def test_step_failure_and_soft_assertions(pytester: pytest.Pytester) -> None:
    """Verify soft assertions on steps include step IDs in consolidated summaries."""
    pytester.makepyfile(
        """
        from pytest_verifies import step

        def test_soft_steps():
            # Soft action step fails; execution continues
            with step("STEP-01", description="Configure rig", soft=True):
                assert False, "Rig setup failed"

            # Soft verification step fails; execution continues
            with step("STEP-02", description="Check voltage", verifies="REQ-PWR-001", soft=True):
                assert False, "Voltage 4.2 != 5.0"

            # Passing step
            with step("STEP-03", description="Teardown"):
                assert True
        """
    )

    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    stdout = result.stdout.str()
    assert "[ACTION] [Step: STEP-01]" in stdout
    assert "Rig setup failed" in stdout
    assert "[REQ-PWR-001] [Step: STEP-02]" in stdout
    assert "Voltage 4.2 != 5.0" in stdout


def test_step_reporting_and_combiner(pytester: pytest.Pytester) -> None:
    """Verify combine CLI generates CSV, JSON, HTML, and MD with step information."""
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "REQ-PWR-001",
                        "title": "Nominal Power Rail",
                        "priority": "HIGH",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        from pytest_verifies import step

        def test_protocol():
            with step("STEP-INIT", description="Initialise stimulus"):
                assert True

            with step("STEP-CHECK", description="Check power rail", verifies="REQ-PWR-001"):
                assert True
        """
    )

    shards_dir = pytester.path / "shards"
    res_run = pytester.runpytest(f"--verifies-out={shards_dir}", "--verifies-stage=unit")
    res_run.assert_outcomes(passed=1)

    csv_out = pytester.path / "report.csv"
    json_out = pytester.path / "report.json"
    html_out = pytester.path / "report.html"
    md_out = pytester.path / "report.md"

    res_cli = pytester.run(
        "pytest-verifies",
        "combine",
        str(shards_dir),
        "--baseline",
        str(baseline_file),
        "--csv",
        str(csv_out),
        "--json",
        str(json_out),
        "--html",
        str(html_out),
        "--md",
        str(md_out),
    )
    assert res_cli.ret == 0

    # 1. Check CSV report has 'steps' column and STEP-CHECK
    csv_text = csv_out.read_text(encoding="utf-8")
    assert "steps" in csv_text
    assert "STEP-CHECK" in csv_text

    # 2. Check JSON report
    json_data = json.loads(json_out.read_text(encoding="utf-8"))
    req_entry = json_data["requirements"][0]
    assert "STEP-CHECK" in req_entry["steps"]
    # Check test_records in JSON
    action_records = [r for r in json_data["test_records"] if r.get("step_id") == "STEP-INIT"]
    assert len(action_records) == 1
    assert action_records[0]["req_ids"] == []

    # 3. Check HTML report contains step badge and action steps section
    html_text = html_out.read_text(encoding="utf-8")
    assert "Test Procedure Action Steps" in html_text
    assert "STEP-INIT" in html_text
    assert "badge-step" in html_text

    # 4. Check Markdown report contains action steps section and step tag
    md_text = md_out.read_text(encoding="utf-8")
    assert "## Test Procedure Action Steps" in md_text
    assert "STEP-INIT" in md_text
    assert "[Step: `STEP-CHECK`]" in md_text
