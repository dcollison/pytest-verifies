# Multi-Run Shard Consolidation

In complex software architectures and CI/CD pipelines, automated tests run across different execution environments, stages, and test tiers.

---

## The Shard Architecture

Modelled after `coverage.py`, individual Pytest runs output worker-safe `.jsonl` shard files tagged with stage labels:

```bash
# Stage 1: Unit tests
uv run pytest tests/unit --verifies-out=.verifies --verifies-stage=unit

# Stage 2: Integration tests
uv run pytest tests/integration --verifies-out=.verifies --verifies-stage=integration

# Stage 3: End-to-end system tests
uv run pytest tests/system --verifies-out=.verifies --verifies-stage=system
```

Each run generates a unique timestamped shard file:
```text
.verifies/
├── verifies.unit.20261015T080000Z.a1b2c3d4.jsonl
├── verifies.integration.20261015T081500Z.e5f6a7b8.jsonl
└── verifies.system.20261015T083000Z.c9d0e1f2.jsonl
```

---

## Combining Shards via Standalone CLI

Run `pytest-verifies combine` to aggregate all shards across tiers against your baseline:

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

### Deterministic Status Resolution

For each requirement across all runs and stages:
* **`PASS`**: At least one test passed (`PASSED` or `XPASS`), and zero tests failed, skipped, or had stage disparities.
* **`PARTIAL`**: Displayed when a requirement has passed in at least one test/stage, but also has failures, skips, or stage disparities in others.
* **`FAIL`**: All test executions failed or were unverified (e.g. declared in baseline but never executed, or all runs were `SKIPPED`).
