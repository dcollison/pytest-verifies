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

---

## 5. Test Procedure Steps & Action Steps

In formal engineering verification (such as ISO 26262, IEC 62304, or DO-178C test protocols), test specifications define explicit **Step IDs** (e.g. `STEP-01`, `1.1`). These steps fall into two categories:

1. **Action Steps (Stimulus / Setup):** Perform state transitions, calibration, or stimulus without directly validating a requirement.
2. **Verification Steps:** Directly assert system behaviour against one or more requirements.

Import `step` alongside `verifies`:

```python
from pytest_verifies import step, verifies


def test_battery_depletion_sequence():
    # 1. Pure Action Step: No requirement verified
    with step("STEP-01", description="Connect battery simulator and set initial SOC"):
        sim.connect()
        sim.set_soc(100)

    # 2. Action Step with Telemetry Evidence
    with step("STEP-02", description="Discharge at 2C rate") as s:
        current_a = sim.discharge(rate="2C")
        s.attach("discharge_current_a", current_a)

    # 3. Verification Step using step(..., verifies=...)
    with step("STEP-03", description="Verify low-charge cutoff trigger", verifies="REQ-BAT-004"):
        assert sim.cutoff_tripped is True

    # 4. Verification Step using verifies(..., step=...)
    with verifies("REQ-BAT-005", step="STEP-04", description="Verify low-charge alarm packet"):
        assert sim.alarm_active("LOW_BATTERY") is True
```

### Benefits of Step Tracking
* **Failure Attribution:** If an action step fails (e.g. a timeout during `STEP-01`), the failure report clearly attributes the issue to the action step without falsely recording requirement defects.
* **Audit Trail:** Reports include a complete test procedure walkthrough table matching your formal verification protocol.
* **ALM / PLM Synchronization:** Step IDs export directly to the `steps` column in CSV and JSON for tools like Polarion, Jira Xray, and Jama.
