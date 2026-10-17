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
            # 1. Action step: Prepare play area
            with step("STEP-01", description="Prepare puppy play area") as s1:
                s1.attach("leash_ready", True)
                status = "ready"
                assert status == "ready"

            # 2. Verification step using step(..., verifies=...)
            with step("STEP-02", description="Verify puppy comes when called", verifies="REQ-DOG-001"):
                assert 200 == 200

            # 3. Verification step using verifies(..., step=...)
            with verifies("REQ-DOG-002", step="STEP-03", description="Verify puppy wags tail"):
                tail_wag_speed = 50
                assert tail_wag_speed > 0
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
    assert records[0]["description"] == "Prepare puppy play area"
    assert records[0]["evidence"] == {"leash_ready": True}

    # Record 2: Verification step via step(...)
    assert records[1]["step_id"] == "STEP-02"
    assert records[1]["req_ids"] == ["REQ-DOG-001"]
    assert records[1]["status"] == "PASSED"

    # Record 3: Verification step via verifies(...)
    assert records[2]["step_id"] == "STEP-03"
    assert records[2]["req_ids"] == ["REQ-DOG-002"]
    assert records[2]["status"] == "PASSED"


def test_step_failure_and_soft_assertions(pytester: pytest.Pytester) -> None:
    """Verify soft assertions on steps include step IDs in consolidated summaries."""
    pytester.makepyfile(
        """
        from pytest_verifies import step

        def test_soft_steps():
            # Soft action step fails; execution continues
            with step("STEP-01", description="Fetch tennis ball", soft=True):
                assert False, "Tennis ball lost under sofa!"

            # Soft verification step fails; execution continues
            with step("STEP-02", description="Verify puppy barks on command", verifies="REQ-DOG-001", soft=True):
                assert False, "Puppy distracted by butterfly!"

            # Passing step
            with step("STEP-03", description="Reward puppy with belly rub"):
                assert True
        """
    )

    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    stdout = result.stdout.str()
    assert "[ACTION] [Step: STEP-01]" in stdout
    assert "Tennis ball lost under sofa!" in stdout
    assert "[REQ-DOG-001] [Step: STEP-02]" in stdout
    assert "Puppy distracted by butterfly!" in stdout


def test_step_reporting_and_combiner(pytester: pytest.Pytester) -> None:
    """Verify combine CLI generates CSV, JSON, HTML, and MD with step information."""
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "REQ-DOG-001",
                        "text": "Dogs must be able to bark",
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
            with step("STEP-INIT", description="Call puppy to training mat"):
                assert True

            with step("STEP-CHECK", description="Verify puppy barks on command", verifies="REQ-DOG-001"):
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
