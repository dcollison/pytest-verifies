# Assertions, Contexts & Evidence

## Overview

`pytest-verifies` relies strictly on native Python `assert` statements. This ensures full compatibility with Pytest's AST rewriting, providing rich assertion diffs without introducing proprietary assertion wrappers.

---

## 1. Function and Class Decorators

Use `@verifies(...)` on test functions or test classes:

```python
from pytest_verifies import verifies


@verifies("REQ-SYS-001", "REQ-SYS-002", description="Subsystem boot sequence")
def test_subsystem_boot():
    assert True
```

When decorating a test class, all test methods within the class automatically inherit verification tracking for the specified requirements:

```python
@verifies("REQ-COMMS-001")
class TestSerialComms:
    def test_parity(self):
        assert True

    def test_stop_bits(self):
        assert True
```

---

## 2. Context Manager

Use `with verifies(...)` for statement-level or multi-block verification:

```python
from pytest_verifies import verifies


def test_packet_flow():
    # Single-line check
    with verifies("REQ-NET-001"):
        assert 1 == 1

    # Multi-statement block
    with verifies("REQ-NET-002", description="Payload checksum validation"):
        calculated_crc = 0xABCD
        expected_crc = 0xABCD
        assert calculated_crc == expected_crc
```

---

## 3. Soft Assertions

In standard Pytest execution, the first failed assertion aborts the test function. In engineering verification, it is often necessary to check several independent safety limits even if an earlier check fails.

Enable soft assertions per block with `soft=True`, or globally across all blocks with `--verifies-soft`:

```python
from pytest_verifies import verifies


def test_safety_envelope():
    # Block 1 fails softly; execution continues!
    with verifies("REQ-LIM-001", soft=True):
        assert 10 > 20

    # Block 2 executes and records VERIFIED
    with verifies("REQ-LIM-002", soft=True):
        assert 50 == 50

    # At the end of test_safety_envelope, Pytest consolidates failures and fails the test.
```

---

## 4. Objective Evidence Attachment

Audit frameworks require verifiable proof of test outcomes. Objective evidence can be provided statically or dynamically:

```python
from pytest_verifies import verifies


def test_sensor_telemetry():
    # Static evidence dictionary
    with verifies("REQ-SNS-001", evidence={"sensor_model": "BMP390", "calibrated": True}):
        assert True

    # Dynamic attachment during runtime
    with verifies("REQ-SNS-002") as ctx:
        measured_pressure_hpa = 1013.25
        ctx.attach("pressure_hpa", measured_pressure_hpa)
        ctx.record_evidence({"drift_pct": 0.01})
        assert measured_pressure_hpa > 900.0
```
