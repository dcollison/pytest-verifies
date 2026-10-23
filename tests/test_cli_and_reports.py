"""Tests for multi-run shard combining, CLI commands, baseline manifests, and report generation."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from pytest_verifies.baseline import load_baseline
from pytest_verifies.cli import main as cli_main


def test_baseline_loader_formats(tmp_path: Path) -> None:
    """Verify loading baseline requirements manifests from JSON, CSV, and YAML formats."""
    # 1. JSON Format
    json_path = tmp_path / "baseline.json"
    json_path.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "text": "Dogs must be able to bark",
                    },
                    {
                        "id": "REQ-002",
                        "text": "Cats must be able to purr",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    base_json = load_baseline(json_path)
    assert len(base_json) == 2
    assert base_json["REQ-001"].text == "Dogs must be able to bark"
    assert base_json["REQ-002"].text == "Cats must be able to purr"

    # 2. CSV Format with id and text
    csv_path = tmp_path / "baseline.csv"
    csv_path.write_text(
        "id,text\n"
        "REQ-003,Puppies must take afternoon naps\n"
        "REQ-004,Kittens must chase yarn balls\n",
        encoding="utf-8",
    )
    base_csv = load_baseline(csv_path)
    assert len(base_csv) == 2
    assert base_csv["REQ-003"].text == "Puppies must take afternoon naps"
    assert base_csv["REQ-004"].text == "Kittens must chase yarn balls"

    # CSV with alternative 'description' header
    csv_desc_path = tmp_path / "baseline_desc.csv"
    csv_desc_path.write_text(
        "id,description\nREQ-005,Dogs must wag their tails\n",
        encoding="utf-8",
    )
    base_desc = load_baseline(csv_desc_path)
    assert base_desc["REQ-005"].text == "Dogs must wag their tails"

    # 3. YAML Format
    yaml_path = tmp_path / "baseline.yaml"
    yaml_path.write_text(
        "requirements:\n  - id: REQ-006\n    text: Cats must land on their feet\n",
        encoding="utf-8",
    )
    base_yaml = load_baseline(yaml_path)
    assert len(base_yaml) == 1
    assert base_yaml["REQ-006"].text == "Cats must land on their feet"

    # 4. Error cases
    non_existent = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_baseline(non_existent)

    bad_suffix = tmp_path / "baseline.txt"
    bad_suffix.write_text("id: 1", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported baseline file format"):
        load_baseline(bad_suffix)


def test_multi_run_shard_combining_and_stage_consolidation(pytester: pytest.Pytester) -> None:
    """Simulate two stages (unit and system) where REQ-1 passes unit but fails system, resolving to FAILED."""
    shards_dir = pytester.path / ".verifies"

    # Write baseline manifest
    baseline_path = pytester.path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "text": "Dogs must be able to bark",
                    },
                    {"id": "REQ-002", "text": "Dogs must wag their tails"},
                    {"id": "REQ-003", "text": "Cats must be able to purr"},
                ]
            }
        ),
        encoding="utf-8",
    )

    # Stage 1: Unit tests (REQ-1 passes, REQ-2 passes)
    pytester.makepyfile(
        test_unit="""
        from pytest_verifies import verifies

        def test_unit_req1():
            with verifies("REQ-001"):
                assert True

        def test_unit_req2():
            with verifies("REQ-002"):
                assert True
        """
    )
    result_unit = pytester.runpytest(
        "test_unit.py",
        f"--verifies-out={shards_dir}",
        "--verifies-stage=unit",
    )
    result_unit.assert_outcomes(passed=2)

    # Stage 2: System tests (REQ-1 fails in system integration, REQ-2 not executed, REQ-3 not executed)
    pytester.makepyfile(
        test_system="""
        from pytest_verifies import verifies

        def test_system_req1():
            with verifies("REQ-001"):
                assert False, "Puppy distracted by butterfly during park test"
        """
    )
    result_system = pytester.runpytest(
        "test_system.py",
        f"--verifies-out={shards_dir}",
        "--verifies-stage=system",
    )
    result_system.assert_outcomes(failed=1)

    # Now execute the standalone CLI to combine shards
    json_out = pytester.path / "out.json"
    csv_out = pytester.path / "out.csv"
    md_out = pytester.path / "out.md"
    html_out = pytester.path / "out.html"

    cli_exit = cli_main(
        [
            "combine",
            str(shards_dir),
            f"--baseline={baseline_path}",
            f"--json={json_out}",
            f"--csv={csv_out}",
            f"--md={md_out}",
            f"--html={html_out}",
        ]
    )

    # Quality gate must fail because REQ-001 failed in the system stage!
    assert cli_exit == 1

    # Verify JSON output
    assert json_out.is_file()
    json_data = json.loads(json_out.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in json_data["requirements"]}

    # REQ-001 passed in unit, failed in system -> overall consolidated status PARTIAL
    assert reqs["REQ-001"]["status"] == "PARTIAL"
    assert reqs["REQ-001"]["stages_verified"] == {"unit": "PASS", "system": "FAIL"}
    assert len(reqs["REQ-001"]["failure_messages"]) == 1
    assert "Puppy distracted by butterfly" in reqs["REQ-001"]["failure_messages"][0]

    # REQ-002 passed in unit -> overall consolidated status PASS
    assert reqs["REQ-002"]["status"] == "PASS"
    assert reqs["REQ-002"]["stages_verified"] == {"unit": "PASS"}

    # REQ-003 was in baseline but not executed in any stage -> FAIL
    assert reqs["REQ-003"]["status"] == "FAIL"

    # Summary metrics: 1 pass out of 3 baseline reqs = 33.33%
    assert json_data["summary"]["total_baseline_requirements"] == 3
    assert json_data["summary"]["passed_count"] == 1
    assert json_data["summary"]["verified_count"] == 1
    assert json_data["summary"]["failed_count"] == 1
    assert json_data["summary"]["partial_count"] == 1
    assert json_data["summary"]["unverified_count"] == 1
    assert json_data["summary"]["coverage_percentage"] == pytest.approx(33.33, 0.1)

    # Verify CSV output
    assert csv_out.is_file()
    with csv_out.open("r", encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 3
        csv_map = {row["req_id"]: row for row in reader}
        assert csv_map["REQ-001"]["status"] == "PARTIAL"
        assert "unit:PASS" in csv_map["REQ-001"]["stages"]
        assert "system:FAIL" in csv_map["REQ-001"]["stages"]
        assert csv_map["REQ-002"]["status"] == "PASS"
        assert csv_map["REQ-003"]["status"] == "FAIL"

    # Verify Markdown output
    assert md_out.is_file()
    md_content = md_out.read_text(encoding="utf-8")
    assert "# Requirements Traceability Matrix (RTM)" in md_content
    assert "## Summary Scorecard" in md_content
    assert "REQ-001" in md_content
    assert "Puppy distracted by butterfly" in md_content

    # Verify HTML output
    assert html_out.is_file()
    html_content = html_out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert "Requirements Traceability Matrix" in html_content
    assert "REQ-001" in html_content
    assert "status-fail" in html_content
    assert "searchInput" in html_content


def test_cli_disallow_orphans_quality_gate(pytester: pytest.Pytester) -> None:
    """Verify --disallow-orphans fails when an unmanifested requirement ID is observed."""
    shards_dir = pytester.path / "shards"
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps({"requirements": [{"id": "REQ-VALID-01", "text": "Dogs must bark"}]}),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_both():
            with verifies("REQ-VALID-01"):
                assert True
            with verifies("REQ-UNTRACKED-99"):
                assert True
        """
    )
    result = pytester.runpytest(f"--verifies-out={shards_dir}")
    result.assert_outcomes(passed=1)

    # Run combine CLI with --disallow-orphans
    exit_code = cli_main(
        [
            "combine",
            str(shards_dir),
            f"--baseline={baseline_file}",
            "--disallow-orphans",
        ]
    )
    assert exit_code == 1


def test_cli_fail_under_threshold(pytester: pytest.Pytester) -> None:
    """Verify --fail-under fails when verified requirement coverage is below specified threshold."""
    shards_dir = pytester.path / "shards"
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "requirements": [
                    {"id": "REQ-1"},
                    {"id": "REQ-2"},
                    {"id": "REQ-3"},
                    {"id": "REQ-4"},
                ]
            }
        ),
        encoding="utf-8",
    )

    # Only verify REQ-1 (25% coverage)
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_single():
            with verifies("REQ-1"):
                assert True
        """
    )
    result = pytester.runpytest(f"--verifies-out={shards_dir}")
    result.assert_outcomes(passed=1)

    # Should fail with --fail-under 50.0
    exit_fail = cli_main(
        [
            "combine",
            str(shards_dir),
            f"--baseline={baseline_file}",
            "--fail-under=50.0",
        ]
    )
    assert exit_fail == 1

    # Should pass with --fail-under 20.0
    exit_pass = cli_main(
        [
            "combine",
            str(shards_dir),
            f"--baseline={baseline_file}",
            "--fail-under=20.0",
        ]
    )
    assert exit_pass == 0


def test_cli_direct_subcommand_invocation(pytester: pytest.Pytester) -> None:
    """Verify invoking the installed console script executable directly."""
    shards_dir = pytester.path / "shards"
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_ok():
            with verifies("REQ-EXEC-1"):
                assert True
        """
    )
    result = pytester.runpytest(f"--verifies-out={shards_dir}")
    result.assert_outcomes(passed=1)

    res = subprocess.run(
        [sys.executable, "-m", "pytest_verifies.cli", "combine", str(shards_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Requirements Traceability Matrix" in res.stdout
    assert "Pass: 1" in res.stdout


def test_console_summary_color_and_partial(pytester: pytest.Pytester) -> None:
    """Verify console output renders summary table with --color=yes and displays partial status."""
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "requirements": [
                    {"id": "REQ-PASS", "text": "Happy golden retriever"},
                    {"id": "REQ-FAIL", "text": "Grumpy guard dog"},
                    {"id": "REQ-PART", "text": "Curious ginger kitten"},
                ]
            }
        ),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import verifies

        def test_pass():
            with verifies("REQ-PASS"):
                assert True

        def test_fail():
            with verifies("REQ-FAIL"):
                assert False

        def test_part_pass():
            with verifies("REQ-PART"):
                assert True

        @pytest.mark.skip(reason="Partial requirement skip")
        @verifies("REQ-PART")
        def test_part_skip():
            assert True
        """
    )

    result = pytester.runpytest(
        f"--verifies-baseline={baseline_file}",
        "--color=yes",
    )
    result.assert_outcomes(passed=2, failed=1, skipped=1)

    # Check that console summary table was emitted with ordered rows
    result.stdout.fnmatch_lines(
        [
            "*Requirements Traceability Matrix (RTM)*",
            "*REQ-FAIL*FAIL*",
            "*REQ-PART*PARTIAL*",
            "*REQ-PASS*PASS*",
            "*Total: 3*Pass: 1*Fail: 1*Partial: 1*",
        ]
    )


def test_baseline_loader_edge_cases(tmp_path: Path) -> None:
    """Verify baseline loader handles title/requirement keys, dict formats, None values, and invalid inputs."""
    # 1. Key-value dict format with title, requirement, scalar, None, and whitespace fallback
    dict_json = tmp_path / "dict_baseline.json"
    dict_json.write_text(
        json.dumps(
            {
                "REQ-KV-1": {"text": "   ", "title": "Title based text"},
                "REQ-KV-2": {"requirement": "Requirement key text"},
                "REQ-KV-3": "Scalar text",
                "REQ-KV-4": None,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_baseline(dict_json)
    assert loaded["REQ-KV-1"].text == "Title based text"
    assert loaded["REQ-KV-2"].text == "Requirement key text"
    assert loaded["REQ-KV-3"].text == "Scalar text"
    assert loaded["REQ-KV-4"].text == ""

    # 2. Empty key in dict format must raise ValueError
    empty_key_json = tmp_path / "empty_key.json"
    empty_key_json.write_text(json.dumps({"   ": "Invalid empty key"}), encoding="utf-8")
    with pytest.raises(ValueError, match="empty requirement ID"):
        load_baseline(empty_key_json)

    # 3. Empty YAML file (yaml.safe_load returns None) must raise ValueError
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected dict or list"):
        load_baseline(empty_yaml)

    # 4. CSV with whitespace-only trailing rows (both 1-column and multi-column)
    csv_file = tmp_path / "trailing_ws.csv"
    csv_file.write_text("id,title\nREQ-CSV-1,CSV Title\n   \n  ,  \n", encoding="utf-8")
    csv_loaded = load_baseline(csv_file)
    assert len(csv_loaded) == 1
    assert csv_loaded["REQ-CSV-1"].text == "CSV Title"

    csv_1col = tmp_path / "single_col.csv"
    csv_1col.write_text("id\nREQ-1COL\n   \n", encoding="utf-8")
    csv_1col_loaded = load_baseline(csv_1col)
    assert list(csv_1col_loaded.keys()) == ["REQ-1COL"]

    # 5. CLI --disallow-orphans without --baseline must fail with exit code 1
    assert cli_main(["combine", str(tmp_path), "--disallow-orphans"]) == 1


def test_shard_stage_sanitisation_and_malformed_jsonl_resilience(tmp_path: Path) -> None:
    """Verify write_shard sanitises stage names for Windows filenames and read_shards ignores malformed entries."""
    from pytest_verifies.models import VerificationRecord
    from pytest_verifies.storage import read_shards, write_shard

    shards_dir = tmp_path / "shards"
    rec = VerificationRecord(
        nodeid="tests/test_sample.py::test_one",
        req_ids=["REQ-SAFE-1"],
        status="PASSED",
        stage="ci/linux:py312\\x64",
    )
    shard_path = write_shard(shards_dir, stage="ci/linux:py312\\x64", records=[rec])
    assert shard_path.is_file()
    assert ":" not in shard_path.name
    assert "/" not in shard_path.name
    assert "\\" not in shard_path.name

    # Append malformed lines, non-dict JSON values, invalid duration_s, and null/whitespace fields
    with shard_path.open("a", encoding="utf-8") as f:
        f.write("{invalid json\n")
        f.write("[1, 2, 3]\n")
        f.write('"just a string"\n')
        f.write("42\n")
        f.write(
            json.dumps(
                {
                    "type": "record",
                    "nodeid": "test_bad_duration",
                    "req_ids": ["REQ-BAD"],
                    "status": "PASSED",
                    "duration_s": "not-a-float",
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "type": "record",
                    "nodeid": "test_strip_reqs",
                    "req_ids": ["", "   ", "  REQ-CLEAN-2  "],
                    "status": "PASSED",
                    "stage": None,
                    "location": None,
                    "step_id": 101,
                    "timestamp": None,
                }
            )
            + "\n"
        )

    runs, records = read_shards([shards_dir])
    assert len(runs) == 1
    assert runs[0]["stage"] == "ci/linux:py312\\x64"
    assert len(records) == 2
    assert records[0].req_ids == ["REQ-SAFE-1"]
    assert records[1].req_ids == ["REQ-CLEAN-2"]
    assert records[1].stage == "default"
    assert records[1].location == ""
    assert records[1].step_id == "101"
    assert records[1].timestamp == ""


def test_html_partial_filter_and_markdown_table_escaping(tmp_path: Path) -> None:
    """Verify HTML report includes Partial filter button/logic and Markdown report escapes pipes/newlines."""
    from pytest_verifies.models import BaselineRequirement, VerificationRecord
    from pytest_verifies.reporters import generate_html_report, generate_markdown_report
    from pytest_verifies.storage import consolidate_requirements

    baseline = {
        "REQ-PIPE-1": BaselineRequirement(
            id="REQ-PIPE-1",
            text="Must handle A | B\nand second line",
        )
    }
    records = [
        VerificationRecord(
            nodeid="test_mod.py::test_pass",
            req_ids=["REQ-PIPE-1"],
            status="PASSED",
            stage="unit",
        ),
        VerificationRecord(
            nodeid="test_mod.py::test_skip",
            req_ids=["REQ-PIPE-1"],
            status="SKIPPED",
            stage="integration",
        ),
        VerificationRecord(
            nodeid="test_mod.py::test_pass",
            req_ids=[],
            step_id="STEP-ACT-1",
            status="PASSED",
            description="Step with | pipe\nand newline",
        ),
    ]

    report = consolidate_requirements(records, baseline=baseline)
    assert report.partial_count == 1
    assert report.requirements[0].is_partial is True
    assert report.requirements[0].display_status == "PARTIAL"

    html_out = generate_html_report(report)
    assert 'data-filter="partial">Partial (1)</button>' in html_out
    assert "matchesFilter = (status === currentFilter);" in html_out
    assert 'data-status="partial"' in html_out

    md_out = generate_markdown_report(report)
    assert r"Must handle A \| B and second line" in md_out
    assert r"Step with \| pipe and newline" in md_out


def test_one_pass_one_fail_same_requirement_gives_partial(pytester: pytest.Pytester) -> None:
    """Verify that when two tests verify the same requirement, one passing and one failing,
    the overall consolidated requirement status is PARTIAL rather than FAIL.
    """
    baseline_file = pytester.path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "requirements": [
                    {"id": "REQ-SAME", "text": "Requirement verified by multiple tests"},
                ]
            }
        ),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_same_pass():
            with verifies("REQ-SAME"):
                assert True

        def test_same_fail():
            with verifies("REQ-SAME"):
                assert False, "Something broke"
        """
    )

    json_out = pytester.path / "rtm.json"
    result = pytester.runpytest(
        f"--verifies-baseline={baseline_file}",
        f"--verifies-json={json_out}",
    )
    result.assert_outcomes(passed=1, failed=1)

    assert json_out.is_file()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    req = data["requirements"][0]
    assert req["req_id"] == "REQ-SAME"
    assert req["status"] == "PARTIAL"
    assert len(req["failure_messages"]) == 1
    assert "Something broke" in req["failure_messages"][0]
    assert len(req["verified_by_tests"]) == 1

    summary = data["summary"]
    assert summary["partial_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["passed_count"] == 0
