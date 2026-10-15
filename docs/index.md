# pytest-verifies

**Enterprise Requirements Traceability Plugin for Pytest**

`pytest-verifies` connects automated test executions to formal engineering specifications (such as ISO 26262, IEC 62304, DO-178C, and SOC2) and produces audit-ready Requirements Traceability Matrix (RTM) artefacts.

---

## Key Capabilities

* **Native Pytest Assertions:** No custom assertion helper wrappers. Standard Python `assert` statements execute with 100% of Pytest's AST rewriting and rich diff diagnostics preserved.
* **Unified API:** A single `verifies` callable acts as a function/class decorator, context manager, and parametrised mark (`pytest.param(..., marks=verifies(...))`).
* **Soft Verification & Objective Evidence:** Soft assertions (`soft=True` or `--verifies-soft`) record non-fatal failures without halting test execution, capturing dynamic runtime telemetry (`ctx.attach(...)` / `ctx.record_evidence(...)`).
* **Concurrency-Safe (`pytest-xdist`):** Distributed test workers transmit serialised records across IPC via `report.user_properties` without file locks or race conditions.
* **Multi-Run Shard Consolidation:** Modelled after `coverage.py`. Separate execution runs emit atomic `.jsonl` shards, which are merged via the standalone `pytest-verifies combine` CLI.
* **Audit-Ready Multi-Format Artefacts:** Produces structured **JSON**, tabular **CSV**, PR/Step Summary **Markdown**, and interactive single-file **HTML5** reports with zero external network dependencies.
* **Strict Quality Gates:** Enforces requirement coverage thresholds (`--verifies-fail-under`), forbids orphaned requirement IDs (`--verifies-disallow-orphans`), and halts CI on unverified specifications.

---

## Quick Example

```python
from pytest_verifies import verifies

@verifies("REQ-PWR-001", description="Nominal voltage within 5.0 V +/- 2%")
def test_voltage():
    measured_v = 5.02
    assert 4.90 <= measured_v <= 5.10

def test_telemetry():
    with verifies("REQ-PWR-002", soft=True, evidence={"limit_a": 1.5}) as ctx:
        current_a = 1.24
        ctx.attach("measured_a", current_a)
        assert current_a < 1.5
```
