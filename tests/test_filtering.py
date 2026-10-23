"""Tests for requirement-based collection filtering (--req) and baseline orphan validation."""

from __future__ import annotations

import json

import pytest


def test_req_filtering_markers_and_ast(pytester: pytest.Pytester) -> None:
    """Verify --req filters tests by glob pattern using both markers and AST body inspection."""
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        @verifies("REQ-AUTH-LOGIN")
        def test_auth_login():
            assert True

        def test_auth_token():
            # AST body inspection finds this without needing a marker
            with verifies("REQ-AUTH-TOKEN"):
                assert True

        @verifies("REQ-DATA-STORE")
        def test_data_store():
            assert True

        def test_unrelated():
            assert True
        """
    )

    # 1. Filter by REQ-AUTH-*
    result = pytester.runpytest("--req=REQ-AUTH-*")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(
        [
            "*2 deselected*",
        ]
    )

    # 2. Filter by comma-separated patterns
    result_multi = pytester.runpytest("--req=REQ-AUTH-LOGIN,REQ-DATA-*")
    result_multi.assert_outcomes(passed=2)
    result_multi.stdout.fnmatch_lines(
        [
            "*2 deselected*",
        ]
    )

    # 3. Filter with no matches
    result_none = pytester.runpytest("--req=REQ-NONEXISTENT-*")
    result_none.assert_outcomes(passed=0)
    result_none.stdout.fnmatch_lines(
        [
            "*4 deselected*",
        ]
    )


def test_disallow_orphans_collect_only_fails_on_unknown_requirement(
    pytester: pytest.Pytester,
) -> None:
    """Verify --collect-only with --verifies-disallow-orphans fails if unknown requirement is referenced."""
    # Write baseline manifest
    baseline_path = pytester.path / "baseline.json"
    baseline_data = {
        "requirements": [
            {"id": "REQ-KNOWN-1", "title": "First Requirement"},
            {"id": "REQ-KNOWN-2", "title": "Second Requirement"},
        ]
    }
    baseline_path.write_text(json.dumps(baseline_data), encoding="utf-8")

    # Write test file with an orphan requirement
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        @verifies("REQ-KNOWN-1")
        def test_good():
            assert True

        @verifies("REQ-UNKNOWN-99")
        def test_bad():
            assert True
        """
    )

    result = pytester.runpytest(
        "--collect-only",
        f"--verifies-baseline={baseline_path}",
        "--verifies-disallow-orphans",
    )
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "*ERROR: Found orphaned requirement IDs not present in baseline manifest:*",
            "*REQ-UNKNOWN-99*test_bad*",
        ]
    )


def test_disallow_orphans_ast_inspection(pytester: pytest.Pytester) -> None:
    """Verify orphans inside with verifies(...) blocks are detected by static baseline check."""
    baseline_path = pytester.path / "baseline.csv"
    baseline_path.write_text("id,title\nREQ-BASE-1,Base One\n", encoding="utf-8")

    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_inside_body():
            with verifies("REQ-ORPHAN-BODY"):
                assert True
        """
    )

    result = pytester.runpytest(
        f"--verifies-baseline={baseline_path}",
        "--verifies-disallow-orphans",
    )
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "*ERROR: Found orphaned requirement IDs not present in baseline manifest:*",
            "*REQ-ORPHAN-BODY*",
        ]
    )


def test_disallow_orphans_without_baseline_raises_error(pytester: pytest.Pytester) -> None:
    """Verify enabling --verifies-disallow-orphans without specifying a baseline raises UsageError."""
    pytester.makepyfile(
        """
        def test_dummy():
            assert True
        """
    )
    result = pytester.runpytest("--verifies-disallow-orphans")
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        ["*ERROR: --verifies-disallow-orphans requires --verifies-baseline to be specified.*"]
    )


def test_step_positional_description_and_ast_set_asyncwith_filtering(
    pytester: pytest.Pytester,
) -> None:
    """Verify positional description in step() is not treated as an orphan requirement ID and AST handles sets/AsyncWith."""
    baseline_path = pytester.path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "requirements": [
                    {"id": "REQ-BASE-1", "title": "First"},
                    {"id": "REQ-BASE-2", "requirement": "Second"},
                ]
            }
        ),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        from pytest_verifies import step, verifies

        def test_step_positional_args():
            # Positional description on an action step must NOT be treated as a requirement ID
            with step("STEP-01", "Prepare test fixtures"):
                assert True

            # Positional description followed by *req_ids
            with step("STEP-02", "Check first requirement", "REQ-BASE-1"):
                assert True

            # Set literal in verifies(...)
            with verifies({"REQ-BASE-1", "REQ-BASE-2"}):
                assert True
        """
    )

    result = pytester.runpytest(
        f"--verifies-baseline={baseline_path}",
        "--verifies-disallow-orphans",
        "--req=REQ-BASE-2",
    )
    result.assert_outcomes(passed=1)


def test_dynamic_orphan_caught_in_sessionfinish_without_report_flags(
    pytester: pytest.Pytester,
) -> None:
    """Verify runtime/dynamic orphans fail sessionfinish quality gate even when no report flags are passed."""
    baseline_path = pytester.path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"requirements": [{"id": "REQ-KNOWN-1", "text": "Known"}]}),
        encoding="utf-8",
    )

    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_dynamic_orphan():
            dyn_id = "REQ-" + "DYNAMIC-ORPHAN"
            with verifies(dyn_id):
                assert True
        """
    )

    result = pytester.runpytest(
        f"--verifies-baseline={baseline_path}",
        "--verifies-disallow-orphans",
    )
    # Test itself passed, but session exit code must be non-zero due to orphan quality gate
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_collect_only_does_not_fail_coverage_gate_or_write_shards(
    pytester: pytest.Pytester,
) -> None:
    """Verify --collect-only validates static orphans without failing --verifies-fail-under or writing shards."""
    baseline_path = pytester.path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"requirements": [{"id": "REQ-KNOWN-1", "text": "Known"}]}),
        encoding="utf-8",
    )
    shards_dir = pytester.path / "collect_shards"

    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        @verifies("REQ-KNOWN-1")
        def test_valid():
            assert True
        """
    )

    result = pytester.runpytest(
        "--collect-only",
        f"--verifies-baseline={baseline_path}",
        "--verifies-disallow-orphans",
        "--verifies-fail-under=100",
        f"--verifies-out={shards_dir}",
    )
    assert result.ret == 0
    assert not shards_dir.exists()
