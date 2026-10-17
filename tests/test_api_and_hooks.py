"""Tests for the public API, context manager, decorators, soft assertions, and pytest hooks."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from pytest_verifies import verifies


def test_api_validation_errors() -> None:
    """Verify input validation and runtime error constraints on the verifies callable."""
    # Zero requirement IDs should raise ValueError
    with pytest.raises(ValueError, match="At least one non-empty requirement ID"):
        verifies()

    with pytest.raises(ValueError, match="At least one non-empty requirement ID"):
        verifies("")

    # Using context manager outside an active test context should raise RuntimeError
    from pytest_verifies.context import _current_test_nodeid

    token = _current_test_nodeid.set(None)
    try:
        ctx = verifies("REQ-TEST-1")
        with pytest.raises(RuntimeError, match="active pytest test context"):
            with ctx:
                pass
    finally:
        _current_test_nodeid.reset(token)


def test_decorator_and_context_basics(pytester: pytest.Pytester) -> None:
    """Verify basic passing and failing execution for both decorators and context blocks."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import verifies

        @verifies("REQ-DEC-PASS")
        def test_decorator_pass():
            assert 10 == 10

        @verifies("REQ-DEC-FAIL")
        def test_decorator_fail():
            assert 10 == 20

        def test_context_manager_pass():
            with verifies("REQ-CTX-PASS"):
                assert "hello" == "hello"

        def test_context_manager_fail():
            with verifies("REQ-CTX-FAIL"):
                assert [1, 2] == [1, 9]
        """
    )

    report_path = pytester.path / "rtm.json"
    result = pytester.runpytest(f"--verifies-json={report_path}")
    result.assert_outcomes(passed=2, failed=2)

    assert report_path.is_file()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    assert reqs["REQ-DEC-PASS"]["status"] == "VERIFIED"
    assert reqs["REQ-DEC-FAIL"]["status"] == "FAILED"
    assert reqs["REQ-CTX-PASS"]["status"] == "VERIFIED"
    assert reqs["REQ-CTX-FAIL"]["status"] == "FAILED"


def test_single_line_assertion_diff_preservation(pytester: pytest.Pytester) -> None:
    """Verify single-line with verifies(...): assert diff preserves native pytest rich assertion details."""
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_packet_diff():
            left = {"protocol": "TCP", "port": 80}
            right = {"protocol": "TCP", "port": 443}
            with verifies("REQ-PORT"): assert left == right
        """
    )

    report_path = pytester.path / "rtm.json"
    result = pytester.runpytest(f"--verifies-json={report_path}")
    result.assert_outcomes(failed=1)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    req = [r for r in data["requirements"] if r["req_id"] == "REQ-PORT"][0]
    assert req["status"] == "FAILED"
    assert len(req["failure_messages"]) > 0
    failure_text = req["failure_messages"][0]
    # Check that native pytest diff elements are captured in the failure message
    assert "80" in failure_text
    assert "443" in failure_text


def test_soft_assertions_multi_block(pytester: pytest.Pytester) -> None:
    """Verify soft=True blocks continue execution after failure, collecting all outcomes and failing at end."""
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_multi_safety_limits():
            # Block 1 fails softly
            with verifies("REQ-SOFT-1", soft=True):
                assert 10 > 20

            # Execution continues to Block 2 which passes
            with verifies("REQ-SOFT-2", soft=True):
                assert 50 == 50

            # Block 3 fails softly
            with verifies("REQ-SOFT-3", soft=True):
                assert "a" == "b"
        """
    )

    report_path = pytester.path / "rtm.json"
    result = pytester.runpytest(f"--verifies-json={report_path}")
    result.assert_outcomes(failed=1)

    # Validate output stdout mentions soft verification failures
    result.stdout.fnmatch_lines(
        [
            "*Soft verification failure(s) (2):*",
            "*[REQ-SOFT-1]*",
            "*[REQ-SOFT-3]*",
        ]
    )

    data = json.loads(report_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    assert reqs["REQ-SOFT-1"]["status"] == "FAILED"
    assert reqs["REQ-SOFT-2"]["status"] == "VERIFIED"
    assert reqs["REQ-SOFT-3"]["status"] == "FAILED"


def test_global_soft_flag(pytester: pytest.Pytester) -> None:
    """Verify --verifies-soft enables soft assertions across standard verifies blocks without soft=True."""
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_global_soft():
            with verifies("REQ-G-1"):
                assert False, "Fail 1"
            with verifies("REQ-G-2"):
                assert True
        """
    )

    report_path = pytester.path / "rtm.json"
    result = pytester.runpytest("--verifies-soft", f"--verifies-json={report_path}")
    result.assert_outcomes(failed=1)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}
    assert reqs["REQ-G-1"]["status"] == "FAILED"
    assert reqs["REQ-G-2"]["status"] == "VERIFIED"


def test_edge_cases_xfail_and_skip(pytester: pytest.Pytester) -> None:
    """Verify behaviour with @pytest.mark.skip and @pytest.mark.xfail."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import verifies

        @pytest.mark.skip(reason="Under maintenance")
        @verifies("REQ-SKIP")
        def test_skipped():
            assert True

        @pytest.mark.xfail(reason="Kitten is currently napping")
        @verifies("REQ-XFAIL")
        def test_expected_failure():
            assert 1 == 0

        @pytest.mark.xfail(reason="Fix landed early")
        @verifies("REQ-XPASS")
        def test_unexpected_pass():
            assert 1 == 1
        """
    )

    report_path = pytester.path / "rtm.json"
    result = pytester.runpytest(f"--verifies-json={report_path}")
    result.assert_outcomes(skipped=1, xfailed=1, xpassed=1)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    # Skipped resolves to UNVERIFIED
    assert reqs["REQ-SKIP"]["status"] == "UNVERIFIED"
    # XFailed resolves to FAILED (known defect blocks requirement verification)
    assert reqs["REQ-XFAIL"]["status"] == "FAILED"
    # XPassed resolves to VERIFIED
    assert reqs["REQ-XPASS"]["status"] == "VERIFIED"


def test_dynamic_evidence_attachment(pytester: pytest.Pytester) -> None:
    """Verify both static and dynamic evidence attachment appear in reports."""
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_puppy_metrics():
            # Static evidence passed into verifies
            with verifies("REQ-EV-1", evidence={"treats_eaten": 4, "happy": True}):
                assert True

            # Dynamic attachment via ctx.attach and ctx.record_evidence
            with verifies("REQ-EV-2") as ctx:
                ctx.attach("favorite_toy", "squeaky bone")
                ctx.record_evidence({"tail_wagging": True})
                assert True
        """
    )

    json_path = pytester.path / "report.json"
    md_path = pytester.path / "report.md"
    html_path = pytester.path / "report.html"

    result = pytester.runpytest(
        f"--verifies-json={json_path}",
        f"--verifies-md={md_path}",
        f"--verifies-html={html_path}",
    )
    result.assert_outcomes(passed=1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    assert reqs["REQ-EV-1"]["evidence"] == [{"treats_eaten": 4, "happy": True}]
    assert reqs["REQ-EV-2"]["evidence"] == [{"favorite_toy": "squeaky bone", "tail_wagging": True}]

    # Verify evidence in Markdown report
    md_text = md_path.read_text(encoding="utf-8")
    assert "treats_eaten" in md_text
    assert "favorite_toy" in md_text
    assert "squeaky bone" in md_text

    # Verify evidence in HTML report
    html_text = html_path.read_text(encoding="utf-8")
    assert "treats_eaten" in html_text
    assert "tail_wagging" in html_text


def test_junit_xml_property_injection(pytester: pytest.Pytester) -> None:
    """Verify standard --junitxml generates <property name="verifies" value="REQ-..." /> tags."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import verifies

        @verifies("REQ-JUNIT-1", "REQ-JUNIT-2")
        def test_with_marker():
            assert True

        def test_with_block():
            with verifies("REQ-JUNIT-3"):
                assert True
        """
    )

    junit_file = pytester.path / "junit.xml"
    result = pytester.runpytest(f"--junitxml={junit_file}")
    result.assert_outcomes(passed=2)

    assert junit_file.is_file()
    tree = ET.parse(junit_file)
    root = tree.getroot()

    properties: list[tuple[str, str]] = []
    for prop in root.findall(".//property"):
        name = prop.attrib.get("name", "")
        val = prop.attrib.get("value", "")
        properties.append((name, val))

    verifies_props = [val for name, val in properties if name == "verifies"]
    assert "REQ-JUNIT-1" in verifies_props
    assert "REQ-JUNIT-2" in verifies_props
    assert "REQ-JUNIT-3" in verifies_props


def test_parametrisation_marks(pytester: pytest.Pytester) -> None:
    """Verify pytest.param(..., marks=verifies(...)) attaches requirements correctly."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import verifies

        @pytest.mark.parametrize(
            "speed, expected",
            [
                pytest.param(10, 100, marks=verifies("REQ-PARAM-10")),
                pytest.param(20, 400, marks=verifies("REQ-PARAM-20")),
            ],
        )
        def test_kinetic_energy(speed, expected):
            assert speed ** 2 == expected
        """
    )

    json_path = pytester.path / "param.json"
    result = pytester.runpytest(f"--verifies-json={json_path}")
    result.assert_outcomes(passed=2)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    req_ids = {r["req_id"] for r in data["requirements"]}
    assert "REQ-PARAM-10" in req_ids
    assert "REQ-PARAM-20" in req_ids


def test_fixture_setup_and_teardown_lifecycle(pytester: pytest.Pytester) -> None:
    """Verify steps/verifies inside setup/teardown fixtures and teardown failures invalidating passed calls."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import step, verifies

        @pytest.fixture
        def managed_env():
            with step("STEP-SETUP", description="Initialise environment"):
                with verifies("REQ-SETUP-1"):
                    assert True
            yield
            with step("STEP-TEARDOWN", description="Clean up environment"):
                with verifies("REQ-TEARDOWN-1"):
                    assert True

        @pytest.fixture
        def failing_teardown():
            yield
            raise RuntimeError("Hardware disconnect crash during teardown")

        @pytest.fixture
        def soft_failing_setup():
            with verifies("REQ-SOFT-SETUP", soft=True):
                assert False, "Soft failure in setup"

        @pytest.fixture(scope="module")
        def module_teardown_soft_fail():
            yield
            with verifies("REQ-MOD-TD-SOFT", soft=True):
                assert False, "Module teardown soft failure"

        @pytest.fixture
        def skipping_teardown():
            yield
            with verifies("REQ-TD-SKIP"):
                pytest.skip("Teardown check skipped")

        @verifies("REQ-CALL-1")
        def test_full_lifecycle(managed_env, module_teardown_soft_fail):
            with step("STEP-CALL", description="Execute main test"):
                assert True

        @verifies("REQ-TD-MARKER")
        def test_teardown_crash_invalidates_marker(failing_teardown):
            assert True

        def test_teardown_crash_invalidates_context(failing_teardown):
            with verifies("REQ-TD-CTX"):
                assert True

        @verifies("REQ-MAIN-NOT-PARTIAL")
        def test_teardown_skip_does_not_corrupt_passed_call(skipping_teardown):
            assert True

        def test_soft_fail_in_setup(soft_failing_setup):
            assert True
        """
    )

    json_path = pytester.path / "lifecycle.json"
    result = pytester.runpytest(f"--verifies-json={json_path}")
    result.assert_outcomes(passed=4, skipped=1, errors=4)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    assert reqs["REQ-SETUP-1"]["status"] == "VERIFIED"
    assert reqs["REQ-CALL-1"]["status"] == "VERIFIED"
    assert reqs["REQ-TEARDOWN-1"]["status"] == "VERIFIED"
    assert reqs["REQ-MOD-TD-SOFT"]["status"] == "FAILED"

    # Teardown skip on REQ-TD-SKIP must NOT attach a SKIPPED record to REQ-MAIN-NOT-PARTIAL
    assert reqs["REQ-MAIN-NOT-PARTIAL"]["status"] == "VERIFIED"
    assert len(reqs["REQ-MAIN-NOT-PARTIAL"]["records"]) == 1
    assert reqs["REQ-MAIN-NOT-PARTIAL"]["records"][0]["status"] == "PASSED"
    assert reqs["REQ-TD-SKIP"]["status"] == "UNVERIFIED"

    # Both marker-based and context-based requirements must be FAILED when teardown crashes
    assert reqs["REQ-TD-MARKER"]["status"] == "FAILED"
    assert any("Hardware disconnect crash" in m for m in reqs["REQ-TD-MARKER"]["failure_messages"])
    assert reqs["REQ-TD-CTX"]["status"] == "FAILED"
    assert any("Hardware disconnect crash" in m for m in reqs["REQ-TD-CTX"]["failure_messages"])

    # Soft failure inside setup fixture must fail the setup phase and record FAILED
    assert reqs["REQ-SOFT-SETUP"]["status"] == "FAILED"

    step_ids = {r["step_id"] for r in data["test_records"] if r.get("step_id")}
    assert {"STEP-SETUP", "STEP-CALL", "STEP-TEARDOWN"} <= step_ids


def test_marker_and_context_deduplication_and_strict_xfail(pytester: pytest.Pytester) -> None:
    """Verify marker deduplication, cross-requirement isolation, strict xfail, and empty AssertionError."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_verifies import step, verifies

        @verifies("REQ-DUP-1")
        def test_same_req_marker_and_failing_block():
            with verifies("REQ-DUP-1"):
                raise AssertionError()

        @verifies("REQ-ISO-PASS", "REQ-ISO-FAIL")
        def test_multi_req_one_passes_one_fails():
            with verifies("REQ-ISO-PASS"):
                assert True
            with verifies("REQ-ISO-FAIL"):
                assert False, "Second requirement failed"

        @verifies("REQ-OUTSIDE-1", "REQ-OUTSIDE-2")
        def test_failure_outside_blocks_fails_all_markers():
            with verifies("REQ-OUTSIDE-1"):
                assert True
            raise RuntimeError("Unhandled crash after block")

        @verifies("REQ-SOFT-THEN-CRASH-PASS", "REQ-SOFT-THEN-CRASH-FAIL")
        def test_soft_failure_followed_by_unhandled_outside_crash():
            with verifies("REQ-SOFT-THEN-CRASH-FAIL", soft=True):
                assert False, "Soft failure in first block"
            with verifies("REQ-SOFT-THEN-CRASH-PASS"):
                assert True
            raise RuntimeError("Unhandled crash outside blocks after soft failure")

        def test_no_marker_crash_after_passing_block():
            with verifies("REQ-NOMARKER-CRASH"):
                assert True
            raise RuntimeError("Unhandled crash in call without marker")

        @verifies("REQ-ACT-SOFT-PASS")
        def test_action_step_soft_failure_invalidates_passed_req():
            with verifies("REQ-ACT-SOFT-PASS", soft=True):
                assert True
            with step("STEP-ACTION-FAIL", soft=True):
                assert False, "Action step failed softly"

        @pytest.mark.xfail(strict=True, reason="Strict xfail should fail on unexpected pass")
        def test_strict_xfail_context():
            with verifies("REQ-STRICT-XFAIL"):
                assert True

        @pytest.mark.parametrize(
            "val",
            [
                pytest.param(
                    1,
                    marks=[
                        verifies("REQ-PARAM-STRICT-XFAIL"),
                        pytest.mark.xfail(strict=True, reason="Param strict xfail"),
                    ],
                )
            ],
        )
        def test_param_strict_xfail(val):
            assert val == 1
        """
    )

    json_path = pytester.path / "dedup.json"
    result = pytester.runpytest(f"--verifies-json={json_path}")
    result.assert_outcomes(failed=8)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    # 1. No duplicate FAILED records when marker and block share REQ-DUP-1, and empty AssertionError() has message
    assert reqs["REQ-DUP-1"]["status"] == "FAILED"
    assert len(reqs["REQ-DUP-1"]["records"]) == 1
    assert reqs["REQ-DUP-1"]["failure_messages"] == ["AssertionError"]

    # 2. REQ-ISO-PASS stays VERIFIED when REQ-ISO-FAIL fails in its own block
    assert reqs["REQ-ISO-PASS"]["status"] == "VERIFIED"
    assert len(reqs["REQ-ISO-PASS"]["records"]) == 1
    assert reqs["REQ-ISO-FAIL"]["status"] == "FAILED"
    assert len(reqs["REQ-ISO-FAIL"]["records"]) == 1

    # 3. Unhandled error outside blocks fails all marker requirements
    assert reqs["REQ-OUTSIDE-1"]["status"] == "FAILED"
    assert reqs["REQ-OUTSIDE-2"]["status"] == "FAILED"

    # 4. Soft failure in one block followed by an unhandled crash outside all blocks fails REQ-SOFT-THEN-CRASH-PASS
    assert reqs["REQ-SOFT-THEN-CRASH-FAIL"]["status"] == "FAILED"
    assert len(reqs["REQ-SOFT-THEN-CRASH-FAIL"]["records"]) == 1
    assert reqs["REQ-SOFT-THEN-CRASH-PASS"]["status"] == "FAILED"

    # 5. Non-marker passing block followed by unhandled crash in same test fails REQ-NOMARKER-CRASH
    assert reqs["REQ-NOMARKER-CRASH"]["status"] == "FAILED"

    # 6. Action step soft failure invalidates passing requirement in the same test
    assert reqs["REQ-ACT-SOFT-PASS"]["status"] == "FAILED"

    # 7. xfail(strict=True) unexpected pass downgrades block PASSED and param marker to FAILED
    assert reqs["REQ-STRICT-XFAIL"]["status"] == "FAILED"
    assert len(reqs["REQ-STRICT-XFAIL"]["failure_messages"]) == 1
    assert reqs["REQ-PARAM-STRICT-XFAIL"]["status"] == "FAILED"


def test_evidence_immutability_and_non_json_types(pytester: pytest.Pytester) -> None:
    """Verify evidence deep-copy isolation and safe serialisation of non-JSON objects."""
    pytester.makepyfile(
        """
        import uuid
        from datetime import datetime, timezone
        from pathlib import Path
        from pytest_verifies import verifies

        def test_evidence_isolation_and_types():
            caller_dict = {"base": 1}
            with verifies("REQ-EV-ISO", evidence=caller_dict) as ctx:
                ctx.attach("added", 2)
                caller_dict["mutated_after"] = 999
                assert True

            assert "added" not in caller_dict

            # Re-using the same context object in a loop must not leak evidence across iterations
            shared_ctx = verifies("REQ-EV-LOOP", evidence={"init": True})
            shared_ctx.attach("pre_enter", "kept")
            for i in range(2):
                with shared_ctx as c:
                    c.attach(f"iter_{i}", i)
                    assert True

            # Non-JSON types: Path, datetime, set, UUID
            with verifies("REQ-EV-TYPES") as ctx:
                ctx.attach("path", Path("/var/log/test.log"))
                ctx.attach("timestamp", datetime(2026, 1, 1, tzinfo=timezone.utc))
                ctx.attach("tags", {"alpha", "beta"})
                ctx.attach("id", uuid.UUID("12345678-1234-5678-1234-567812345678"))
                assert True
        """
    )

    shards_dir = pytester.path / "shards"
    json_path = pytester.path / "ev.json"
    csv_path = pytester.path / "ev.csv"
    md_path = pytester.path / "ev.md"
    html_path = pytester.path / "ev.html"

    result = pytester.runpytest(
        f"--verifies-out={shards_dir}",
        f"--verifies-json={json_path}",
        f"--verifies-csv={csv_path}",
        f"--verifies-md={md_path}",
        f"--verifies-html={html_path}",
    )
    result.assert_outcomes(passed=1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    reqs = {r["req_id"]: r for r in data["requirements"]}

    assert reqs["REQ-EV-ISO"]["evidence"] == [{"base": 1, "added": 2}]
    assert reqs["REQ-EV-LOOP"]["evidence"] == [
        {"init": True, "pre_enter": "kept", "iter_0": 0},
        {"init": True, "pre_enter": "kept", "iter_1": 1},
    ]
    ev_types = reqs["REQ-EV-TYPES"]["evidence"][0]
    assert ev_types["tags"] == ["alpha", "beta"]
    assert ev_types["id"] == "12345678-1234-5678-1234-567812345678"
    assert "2026-01-01" in ev_types["timestamp"]


def test_ini_configuration_options(pytester: pytest.Pytester) -> None:
    """Verify verifies_stage, verifies_out, and verifies_soft work via pytest.ini and CLI overrides."""
    pytester.makeini(
        """
        [pytest]
        verifies_stage = integration
        verifies_out = ini_shards
        verifies_soft = true
        """
    )
    pytester.makepyfile(
        """
        from pytest_verifies import verifies

        def test_from_ini():
            with verifies("REQ-INI-1"):
                assert True
        """
    )

    json_path = pytester.path / "ini.json"
    result = pytester.runpytest(f"--verifies-json={json_path}")
    result.assert_outcomes(passed=1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    req = data["requirements"][0]
    assert req["stages_verified"] == {"integration": "VERIFIED"}
    assert req["records"][0]["location"].startswith("test_ini_configuration_options.py:")
    assert "\\" not in req["records"][0]["location"]

    shard_files = list((pytester.path / "ini_shards").glob("verifies.integration.*.jsonl"))
    assert len(shard_files) == 1

    # CLI --verifies-stage must override pytest.ini
    json_override = pytester.path / "override.json"
    res2 = pytester.runpytest("--verifies-stage=system", f"--verifies-json={json_override}")
    res2.assert_outcomes(passed=1)
    data2 = json.loads(json_override.read_text(encoding="utf-8"))
    assert data2["requirements"][0]["stages_verified"] == {"system": "VERIFIED"}
