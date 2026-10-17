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


@verifies("REQ-AUTH-001", "REQ-AUTH-002", description="User token format and expiration")
def test_jwt_claims():
    payload = {"sub": "user_42", "exp": 1893456000}
    assert payload["exp"] > 1700000000
```

### 3.2 Single-Line Context Manager

Verify fine-grained inline statements while preserving full assertion diffs:

```python
from pytest_verifies import verifies


def test_api_endpoint():
    response = {"status": 200, "content_type": "application/json"}
    with verifies("REQ-API-010"):
        assert response["status"] == 200
```

### 3.3 Soft Assertions & Objective Evidence

Evaluate multiple requirements within a single test execution without early termination on the first failure:

```python
from pytest_verifies import verifies


def test_user_registration():
    email = "developer@example.com"
    request_latency_ms = 45.2

    # Block 1: Soft assertion with static objective evidence
    with verifies(
        "REQ-USER-001",
        description="Valid email address required",
        soft=True,
        evidence={"email": email, "format": "RFC 5322"},
    ):
        assert "@" in email and email.endswith(".com")

    # Block 2: Execution continues even if REQ-USER-001 fails
    with verifies("REQ-PERF-001", soft=True) as ctx:
        ctx.attach("request_latency_ms", request_latency_ms)
        ctx.record_evidence({"cache_hit": True})
        assert request_latency_ms < 100.0
```

### 3.4 Parametrised Tests

Attach requirement tags to specific test parameters:

```python
import pytest
from pytest_verifies import verifies


@pytest.mark.parametrize(
    "discount_code,expected_rate",
    [
        pytest.param("SUMMER10", 0.10, marks=verifies("REQ-PROMO-001")),
        pytest.param("VIP25", 0.25, marks=verifies("REQ-PROMO-002")),
    ],
)
def test_promo_discount_rates(discount_code, expected_rate):
    assert discount_code in ("SUMMER10", "VIP25")
    assert expected_rate > 0.0
```

### 3.5 Test Procedure Steps & Action Steps

Formal test protocols often require tracking discrete step IDs (`STEP-01`, `1.1`), including pure **Action Steps** (setup/fixtures) and **Verification Steps** (checking requirements):

```python
from pytest_verifies import step, verifies


def test_order_checkout_flow():
    # Action step: Setup mock state without validating a requirement
    with step("STEP-01", description="Seed customer cart and catalog items"):
        cart.add_item("item_123", quantity=2)
        cart.apply_promo("WELCOME10")

    # Verification step: Directly validates REQ-CART-001
    with step("STEP-02", description="Verify discount calculation", verifies="REQ-CART-001"):
        assert cart.total_gbp == 90.0

    # Verification step with verifies(..., step=...)
    with verifies("REQ-PAY-002", step="STEP-03", description="Verify payment charge idempotency"):
        charge = payment_gateway.create_charge(idempotency_key="key_abc123")
        assert charge.status == "SUCCEEDED"
```

---

## 4. Pytest Command-Line & Configuration Options

| Option | Ini Configuration | Description |
| :--- | :--- | :--- |
| `--req="PATTERN"` | — | Comma-separated requirement IDs or glob patterns to filter tests (e.g. `--req="REQ-AUTH-*,REQ-PAY-001"`). |
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

Baseline manifests declare formal specifications against which automated tests are verified. Baseline requirements need only an `id` and a requirement statement `text` (or `description`).

### JSON Manifest (`requirements.json`)
```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "text": "Authenticate users using JWT bearer tokens"
    },
    {
      "id": "REQ-002",
      "text": "Rate limiter must throttle exceeding 100 requests per minute"
    }
  ]
}
```

### CSV Manifest (`requirements.csv`)
```csv
id,text
REQ-001,Authenticate users using JWT bearer tokens
REQ-002,Rate limiter must throttle exceeding 100 requests per minute
```

### YAML Manifest (`requirements.yaml`)
```yaml
requirements:
  - id: REQ-001
    text: Authenticate users using JWT bearer tokens
  - id: REQ-002
    text: Rate limiter must throttle exceeding 100 requests per minute
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

# End-to-end / System test tier
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
