# pytest-verifies

[![CI](https://img.shields.io/badge/pytest--verifies-v1.0.0-blue.svg)](https://github.com/your-org/pytest-verifies)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Standards](https://img.shields.io/badge/compliance-ISO%2026262%20%7C%20IEC%2062304%20%7C%20DO--178C%20%7C%20SOC2-orange.svg)](#standards-compliance)

**Enterprise Requirements Traceability Plugin for Pytest.**

`pytest-verifies` seamlessly links automated test suites to formal engineering requirements (such as ISO 26262, IEC 62304, DO-178C, and SOC2) and produces audit-ready Requirements Traceability Matrix (RTM) artefacts.

---

## 1. Core Philosophy & Key Features

1. **Standard Pytest Assertions Only:**
   No custom assertion wrappers. Use native Python `assert` statements inside `with verifies(...)` or on functions decorated with `@verifies(...)`. Pytest's AST assertion rewriting and rich diff diagnostics are 100% preserved.
2. **Unified API:**
   A single callable, `verifies`, functions interchangeably as a function/class decorator, context manager, and parametrised mark (`pytest.param(..., marks=verifies(...))`).
3. **Soft Assertions & Objective Evidence:**
   Support for non-fatal assertions (`soft=True` or `--verifies-soft`) enables tests to evaluate multiple requirements sequentially before reporting consolidated failures. Dynamically attach objective runtime evidence (`ctx.attach("telemetry", value)` or `ctx.record_evidence(dict)`).
4. **`pytest-xdist` Concurrency Safe:**
   Workers never write directly to shared report files or depend on inter-process locks. Verification records are serialised onto `report.user_properties` and transmitted to the controller node.
5. **Multi-Run Shard Consolidation:**
   Modelled after `coverage.py`. Distinct test invocations across disparate execution environments or CI stages (e.g. `unit`, `integration`, `system`) write atomic `.jsonl` shards. The standalone `pytest-verifies combine` CLI merges shards against baseline requirement manifests.
6. **Multi-Format Artefact Generation:**
   Generates structured **JSON**, tabular **CSV**, GitHub/GitLab step summary **Markdown**, and interactive single-file **HTML5** reports with zero external runtime JavaScript or CSS dependencies.
7. **Strict Quality Gates:**
   Enforce requirement coverage thresholds (`--verifies-fail-under`), disallow orphaned requirement IDs (`--verifies-disallow-orphans`), and fail pipelines when known defects or unverified requirements are detected.

---

## 2. Installation

Install using `uv` (recommended):

```bash
uv add pytest-verifies
```

Or using standard Python package managers:

```bash
pip install pytest-verifies
```

---

## 3. Quick Start & Python API

### 3.1 Decorator Usage

Decorate test functions or classes to associate them with one or more requirements:

```python
from pytest_verifies import verifies

@verifies("REQ-PWR-001", "REQ-PWR-002", description="Power rail voltage tolerance")
def test_voltage_limits():
    measured_v = 5.01
    assert 4.95 <= measured_v <= 5.05
```

### 3.2 Single-Line Context Manager

Verify fine-grained inline statements while preserving full assertion diffs:

```python
from pytest_verifies import verifies

def test_network_packet():
    packet = {"protocol": "TCP", "port": 443}
    with verifies("REQ-NET-010"): assert packet["port"] == 443
```

### 3.3 Soft Assertions & Objective Evidence

Evaluate multiple requirements within a single test execution without early termination on the first failure:

```python
from pytest_verifies import verifies

def test_environmental_limits():
    ambient_temp_c = 72.4
    core_voltage_v = 1.18

    # Block 1: Soft assertion with static objective evidence
    with verifies(
        "REQ-ENV-001",
        description="Operating temperature under 85 °C",
        soft=True,
        evidence={"ambient_temp_c": ambient_temp_c, "limit_c": 85.0},
    ):
        assert ambient_temp_c < 85.0

    # Block 2: Execution continues even if REQ-ENV-001 fails
    with verifies("REQ-PWR-003", soft=True) as ctx:
        ctx.attach("core_voltage_v", core_voltage_v)
        ctx.record_evidence({"calibration_offset": 0.02})
        assert 1.15 <= core_voltage_v <= 1.25
```

### 3.4 Parametrised Tests

Attach requirement tags to specific test parameters:

```python
import pytest
from pytest_verifies import verifies

@pytest.mark.parametrize(
    "baud_rate",
    [
        pytest.param(9600, marks=verifies("REQ-COM-001")),
        pytest.param(115200, marks=verifies("REQ-COM-002")),
    ],
)
def test_serial_baud(baud_rate):
    assert baud_rate in (9600, 115200)
```

---

## 4. Pytest Command-Line & Configuration Options

| Option | Ini Configuration | Description |
| :--- | :--- | :--- |
| `--req="PATTERN"` | — | Comma-separated requirement IDs or glob patterns to filter tests (e.g. `--req="REQ-PWR-*,REQ-COM-001"`). |
| `--verifies-out=DIR` | `verifies_out = DIR` | Directory to output `.jsonl` execution shards. |
| `--verifies-stage=NAME` | `verifies_stage = NAME` | Stage label for execution shard (default: `"default"`). |
| `--verifies-baseline=PATH` | `verifies_baseline = PATH` | Path to baseline requirement manifest (`.json`, `.csv`, `.yaml`). |
| `--verifies-soft` | `verifies_soft = true` | Enable soft verification mode globally across all `verifies` blocks. |
| `--verifies-disallow-orphans`| — | Fail collection/session if tests reference IDs not present in baseline. |
| `--verifies-fail-under=NUM` | — | Fail session if verified requirement coverage % is below threshold (0–100). |
| `--verifies-json=PATH` | — | Direct output file for structured JSON RTM report. |
| `--verifies-csv=PATH` | — | Direct output file for tabular CSV RTM report. |
| `--verifies-md=PATH` | — | Direct output file for Markdown summary report. |
| `--verifies-html=PATH` | — | Direct output file for interactive single-file HTML5 report. |

---

## 5. Baseline Requirement Manifests

Baseline manifests declare formal specifications against which automated tests are verified.

### JSON Manifest (`requirements.json`)
```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Power Rail Tolerance",
      "description": "System shall maintain 5.0 V +/- 2%",
      "priority": "HIGH"
    },
    {
      "id": "REQ-002",
      "title": "Thermal Cutoff",
      "description": "Cutoff threshold at 85 °C",
      "priority": "CRITICAL"
    }
  ]
}
```

### CSV Manifest (`requirements.csv`)
```csv
id,title,description,priority
REQ-001,Power Rail Tolerance,System shall maintain 5.0 V +/- 2%,HIGH
REQ-002,Thermal Cutoff,Cutoff threshold at 85 °C,CRITICAL
```

### YAML Manifest (`requirements.yaml`)
```yaml
requirements:
  - id: REQ-001
    title: Power Rail Tolerance
    description: System shall maintain 5.0 V +/- 2%
    priority: HIGH
  - id: REQ-002
    title: Thermal Cutoff
    description: Cutoff threshold at 85 °C
    priority: CRITICAL
```

---

## 6. Multi-Run Shard Consolidation Workflow

In distributed CI pipelines, different test tiers (unit, integration, end-to-end) run in isolated containers. `pytest-verifies` enables merging these shards into a single consolidated matrix:

### Step 1: Run Stage Test Suites
```bash
# Unit test tier
uv run pytest tests/unit --verifies-out=.verifies --verifies-stage=unit

# Integration test tier
uv run pytest tests/integration --verifies-out=.verifies --verifies-stage=integration

# Hardware-in-the-loop / System test tier
uv run pytest tests/system --verifies-out=.verifies --verifies-stage=system
```

### Step 2: Combine Shards via CLI
```bash
uv run pytest-verifies combine .verifies/ \
  --baseline requirements.json \
  --disallow-orphans \
  --fail-under 100.0 \
  --json rtm.json \
  --csv rtm.csv \
  --md rtm.md \
  --html rtm.html
```

### Quality Gate Exit Codes
- **`0`**: Success. All quality gates met (100% of tested requirements verified, coverage threshold met, no orphaned IDs).
- **`1`**: Quality gate failure. One or more requirements failed, orphaned IDs were detected, or verified requirement coverage is below `--fail-under`.

---

## 7. Reporting Artefacts

### Interactive HTML5 Report
Self-contained, responsive, single-file HTML5 document with zero external network dependencies:
- **Metric Cards:** Total Requirements, Verified %, Failed %, Unverified %, Orphan Count.
- **Dynamic Filtering:** Instant filtering by status (`All`, `Verified`, `Failed`, `Unverified`, `Orphans`).
- **Live Search:** Fast search by Requirement ID, title, test nodeid, or file location.
- **Diagnostic Expansion:** Interactive `<details>` sections displaying execution trace, attached objective evidence, and failure tracebacks.

### GitHub / GitLab Markdown Summary
Designed directly for `$GITHUB_STEP_SUMMARY` and merge request comments:
- Summary Scorecard Table with clean status indicators (`VERIFIED`, `FAILED`, `PARTIAL`, `UNVERIFIED`, `[ORPHAN]`).
- Requirements Traceability Table detailing stage coverage and verification tests.
- Collapsible diagnostics with assertion tracebacks and formatted JSON evidence.

### Tabular CSV Export
Standardised format for enterprise PLM / ALM tools (e.g. Jira, Jama, Polarion):
```csv
req_id,title,status,in_baseline,stages,verified_by_tests,evidence,failure_messages
```

---

## 8. Standards Compliance

| Standard | Applicable Clauses | How `pytest-verifies` Supports Compliance |
| :--- | :--- | :--- |
| **ISO 26262** | Part 6, Section 9 & 10 | Provides bidirectional requirements-to-test traceability and verification evidence for ASIL A–D. |
| **IEC 62304** | Section 5.7 & 5.8 | Establishes automated software verification records and RTM reports for Class A–C medical software. |
| **DO-178C** | Section 6.4.4 | Demonstrates verification of software requirements and records objective test execution results. |
| **SOC2 / ISO 27001** | CC7.1, CC7.4 | Auditable proof that automated security controls and regression tests verify baseline control specifications. |

---

## 9. Licence

Distributed under the terms of the **MIT** licence.
