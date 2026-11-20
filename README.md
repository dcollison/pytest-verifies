# pytest-verifies

[![CI](https://github.com/dcollison/pytest-verifies/actions/workflows/ci.yml/badge.svg)](https://github.com/dcollison/pytest-verifies/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://dcollison.github.io/pytest-verifies/)
[![PyPI](https://img.shields.io/pypi/v/pytest-verifies)](https://pypi.org/project/pytest-verifies/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-verifies)](https://pypi.org/project/pytest-verifies/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Enterprise requirements traceability plugin for pytest that links automated test suites to formal engineering requirements (ISO 26262, IEC 62304, DO-178C, SOC2) and produces audit-ready Requirements Traceability Matrix (RTM) artefacts.

## Features

- **Standard Pytest Assertions Only:** Use native Python `assert` statements inside `with verifies(...)` or on functions decorated with `@verifies(...)`. Pytest's AST assertion rewriting and rich diff diagnostics are 100% preserved.
- **Unified API:** A single callable, `verifies`, functions interchangeably as a function/class decorator, context manager, and parametrised mark (`pytest.param(..., marks=verifies(...))`).
- **Soft Assertions & Objective Evidence:** Non-fatal assertions (`soft=True` or `--verifies-soft`) let tests evaluate multiple requirements before reporting consolidated failures, with runtime evidence (`ctx.attach(...)` / `ctx.record_evidence(...)`).
- **Procedure & Action Steps:** Track discrete protocol step IDs (`STEP-01`, `1.1`) across setup/action steps (`step(...)`) and verification steps (`verifies(..., step_id=...)`).
- **`pytest-xdist` Concurrency Safe:** Workers serialise verification records onto `report.user_properties` and transmit them to the controller node without inter-process file locks.
- **Multi-Run Shard Consolidation:** Test tiers (`unit`, `integration`, `system`) emit atomic `.jsonl` shards that `pytest-verifies combine` merges against baseline manifests.
- **Multi-Format Artefact Generation:** Generates structured **JSON**, tabular **CSV**, GitHub/GitLab step summary **Markdown**, and interactive single-file **HTML5** reports with zero external JS/CSS dependencies.
- **Strict Quality Gates:** Enforce coverage thresholds (`--verifies-fail-under`) and disallow orphaned requirement IDs (`--verifies-disallow-orphans`).

## Installation

Install using `uv` (recommended):

```bash
uv add pytest-verifies
```

Or using `pip`:

```bash
pip install pytest-verifies
```

## Quickstart

Create a baseline requirements manifest `requirements.json` (also supports `.csv` and `.yaml`):

```json
{
  "requirements": [
    {
      "id": "REQ-DOG-001",
      "text": "Dogs must be able to bark"
    },
    {
      "id": "REQ-CAT-001",
      "text": "Cats must be able to purr when content"
    }
  ]
}
```

Annotate your pytest tests with `@verifies(...)` or `with verifies(...)`:

```python
from pytest_verifies import verifies


@verifies("REQ-DOG-001", description="Dogs must be friendly and able to bark")
def test_dog_attributes():
    dog = {"name": "Buster", "barks": True}
    assert dog["barks"] is True


def test_cat_purring():
    cat = {"name": "Whiskers", "purring": True}
    with verifies("REQ-CAT-001"):
        assert cat["purring"] is True
```

Run pytest and generate RTM artefacts:

```bash
uv run pytest \
  --verifies-baseline=requirements.json \
  --verifies-md=rtm.md \
  --verifies-html=rtm.html \
  --verifies-json=rtm.json
```

## Python API

### Decorator Usage

Decorate test functions or classes to associate them with one or more requirements:

```python
from pytest_verifies import verifies


@verifies("REQ-DOG-001", "REQ-DOG-002", description="Dogs must be friendly and able to bark")
def test_dog_attributes():
    dog = {"name": "Buster", "species": "Canis familiaris", "barks": True}
    assert dog["barks"] is True
```

### Soft Assertions & Objective Evidence

Evaluate multiple requirements within a single test execution without early termination on the first failure:

```python
from pytest_verifies import verifies


def test_dog_health_and_energy():
    dog = {"name": "Buster", "happy": True, "tail_wags_per_min": 120}

    # Block 1: Soft assertion with static objective evidence
    with verifies(
        "REQ-DOG-002",
        description="Dogs must wag their tails when happy",
        soft=True,
        evidence={"dog_name": dog["name"], "happy": dog["happy"]},
    ):
        assert dog["happy"] is True

    # Block 2: Execution continues even if Block 1 fails
    with verifies("REQ-DOG-003", soft=True) as ctx:
        ctx.attach("tail_wags_per_min", dog["tail_wags_per_min"])
        ctx.record_evidence({"breed": "Golden Retriever"})
        assert dog["tail_wags_per_min"] > 60
```

### Parametrised Tests

Attach requirement tags to specific test parameters:

```python
import pytest
from pytest_verifies import verifies


@pytest.mark.parametrize(
    "animal,sound",
    [
        pytest.param("dog", "woof", marks=verifies("REQ-DOG-001")),
        pytest.param("cat", "meow", marks=verifies("REQ-CAT-001")),
        pytest.param("puppy", "yip", marks=verifies("REQ-DOG-001")),
    ],
)
def test_pet_sounds(animal, sound):
    pet_sounds = {"dog": "woof", "cat": "meow", "puppy": "yip"}
    assert pet_sounds[animal] == sound
```

### Test Procedure Steps & Action Steps

Track discrete step IDs (`STEP-01`, `1.1`), including **Action Steps** (preparing state) and **Verification Steps** (checking requirements):

```python
from pytest_verifies import step, verifies


def test_puppy_training_routine():
    # Action step: Prepare treat and call puppy
    with step("STEP-01", description="Fill treat pouch and call puppy"):
        puppy = {"name": "Buster", "tricks": []}

    # Verification step: Directly validates REQ-DOG-004
    with step("STEP-02", description="Verify puppy sits on command", verifies="REQ-DOG-004"):
        puppy["tricks"].append("sit")
        assert "sit" in puppy["tricks"]

    # Verification step with verifies(..., step_id=...)
    with verifies(
        "REQ-DOG-002", step_id="STEP-03", description="Verify puppy wags tail after treat"
    ):
        tail_wagging = True
        assert tail_wagging is True
```

## Pytest Command-Line & Configuration Options

| Option | Ini Configuration | Description |
| :--- | :--- | :--- |
| `--req="PATTERN"` | — | Comma-separated requirement IDs or glob patterns to filter tests (e.g. `--req="REQ-DOG-*,REQ-CAT-001"`). |
| `--verifies-out=DIR` | `verifies_out = DIR` | Directory to output `.jsonl` execution shards. |
| `--verifies-stage=NAME` | `verifies_stage = NAME` | Stage label for execution shard (default: `"default"`). |
| `--verifies-baseline=PATH` | `verifies_baseline = PATH` | Path to baseline requirement manifest (`.json`, `.csv`, `.yaml`). |
| `--verifies-soft` | `verifies_soft = true` | Enable soft verification mode globally across all `verifies` blocks. |
| `--verifies-disallow-orphans` | — | Fail collection/session if tests reference IDs not present in baseline. |
| `--verifies-fail-under=NUM` | — | Fail session if verified requirement coverage % is below threshold (0–100). |
| `--verifies-json=PATH` | — | Direct output file for structured JSON RTM report. |
| `--verifies-csv=PATH` | — | Direct output file for tabular CSV RTM report. |
| `--verifies-md=PATH` | — | Direct output file for Markdown summary report. |
| `--verifies-html=PATH` | — | Direct output file for interactive single-file HTML5 report. |

## Baseline Requirement Manifests

Baseline manifests declare formal specifications against which automated tests are verified. Requirements require an `id` and a `text` (or `description`) field.

### JSON (`requirements.json`)

```json
{
  "requirements": [
    {
      "id": "REQ-DOG-001",
      "text": "Dogs must be able to bark"
    },
    {
      "id": "REQ-CAT-001",
      "text": "Cats must be able to purr when content"
    }
  ]
}
```

### CSV (`requirements.csv`)

```csv
id,text
REQ-DOG-001,Dogs must be able to bark
REQ-CAT-001,Cats must be able to purr when content
```

### YAML (`requirements.yaml`)

```yaml
requirements:
  - id: REQ-DOG-001
    text: Dogs must be able to bark
  - id: REQ-CAT-001
    text: Cats must be able to purr when content
```

## Multi-Run Shard Consolidation

In distributed CI pipelines, test tiers (`unit`, `integration`, `system`) can emit separate shards and merge them into a consolidated RTM:

```bash
# Step 1: Run stage test suites
uv run pytest tests/unit --verifies-out=.verifies --verifies-stage=unit
uv run pytest tests/integration --verifies-out=.verifies --verifies-stage=integration
uv run pytest tests/system --verifies-out=.verifies --verifies-stage=system

# Step 2: Combine shards via CLI
uv run pytest-verifies combine .verifies/ \
  --baseline requirements.json \
  --disallow-orphans \
  --fail-under 100.0 \
  --json rtm.json \
  --csv rtm.csv \
  --md rtm.md \
  --html rtm.html
```

Exit codes:
- **`0`**: All quality gates met (all tested requirements verified, coverage threshold met, no orphaned IDs).
- **`1`**: Quality gate failure (one or more requirements failed, orphaned IDs detected, or coverage below `--fail-under`).

## Reporting Artefacts

- **Interactive HTML5 (`--verifies-html`):** Self-contained single-file HTML5 report with metric cards, status filtering (`All`, `Pass`, `Partial`, `Fail`, `Orphans`), live search, and expandable execution traces, evidence, and failure tracebacks.
- **GitHub / GitLab Markdown Summary (`--verifies-md`):** Designed for `$GITHUB_STEP_SUMMARY` and PR comments with scorecard tables, stage coverage, and collapsible diagnostics.
- **Tabular CSV (`--verifies-csv`):** Standardised export (`req_id,text,status,in_baseline,stages,tests,evidence,failure_messages`) for PLM/ALM tools such as Jira, Jama, and Polarion. (`stages` is included only when execution stages are configured.)
- **Structured JSON (`--verifies-json`):** Full machine-readable RTM data model including run metadata and verification records.

## Standards Compliance

| Standard | Applicable Clauses | How `pytest-verifies` Supports Compliance |
| :--- | :--- | :--- |
| **ISO 26262** | Part 6, Section 9 & 10 | Provides bidirectional requirements-to-test traceability and verification evidence for ASIL A–D. |
| **IEC 62304** | Section 5.7 & 5.8 | Establishes automated software verification records and RTM reports for Class A–C medical software. |
| **DO-178C** | Section 6.4.4 | Demonstrates verification of software requirements and records objective test execution results. |
| **SOC2 / ISO 27001** | CC7.1, CC7.4 | Auditable proof that automated security controls and regression tests verify baseline control specifications. |

## Documentation

Full documentation is published at [https://dcollison.github.io/pytest-verifies/](https://dcollison.github.io/pytest-verifies/).

To build or preview the docs locally:

```bash
uv sync --group docs
uv run --group docs mkdocs serve
```

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -v
uv run --group docs mkdocs build --strict
```

## Releasing

1. Update the version in `pyproject.toml` and document changes in `CHANGELOG.md`.
2. Tag the release (`vX.Y.Z`) and publish a GitHub Release.
3. `.github/workflows/release.yml` builds the sdist/wheel with `uv build` and publishes to PyPI via Trusted Publishing (OIDC).

## License

MIT License — see [LICENSE](LICENSE).
