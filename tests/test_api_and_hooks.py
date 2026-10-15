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

        @pytest.mark.xfail(reason="Known hardware defect")
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

        def test_telemetry():
            # Static evidence passed into verifies
            with verifies("REQ-EV-1", evidence={"voltage_v": 3.305, "status": "nominal"}):
                assert True

            # Dynamic attachment via ctx.attach and ctx.record_evidence
            with verifies("REQ-EV-2") as ctx:
                ctx.attach("firmware_version", "2.4.1")
                ctx.record_evidence({"crc_verified": True})
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

    assert reqs["REQ-EV-1"]["evidence"] == [{"voltage_v": 3.305, "status": "nominal"}]
    assert reqs["REQ-EV-2"]["evidence"] == [{"firmware_version": "2.4.1", "crc_verified": True}]

    # Verify evidence in Markdown report
    md_text = md_path.read_text(encoding="utf-8")
    assert "3.305" in md_text
    assert "firmware_version" in md_text
    assert "2.4.1" in md_text

    # Verify evidence in HTML report
    html_text = html_path.read_text(encoding="utf-8")
    assert "voltage_v" in html_text
    assert "crc_verified" in html_text


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
