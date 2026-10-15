# Baseline Requirement Manifests

A baseline manifest establishes the master list of requirements that automated tests must verify.

---

## Supported Formats

### 1. JSON (`requirements.json`)

Supports array format or top-level dictionary:

```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Over-current protection",
      "description": "Trigger shutdown if current exceeds 2.0 A",
      "priority": "HIGH"
    },
    {
      "id": "REQ-002",
      "title": "Watchdog heartbeat",
      "priority": "MEDIUM"
    }
  ]
}
```

### 2. CSV (`requirements.csv`)

Requires an `id` column header (case-insensitive):

```csv
id,title,description,priority
REQ-001,Over-current protection,Trigger shutdown if current exceeds 2.0 A,HIGH
REQ-002,Watchdog heartbeat,Periodic timer within 500 ms,MEDIUM
```

### 3. YAML (`requirements.yaml`)

Requires `pyyaml` (installed automatically if using `docs` or `dev` dependency groups):

```yaml
requirements:
  - id: REQ-001
    title: Over-current protection
    priority: HIGH
  - id: REQ-002
    title: Watchdog heartbeat
    priority: MEDIUM
```

---

## Disallowing Orphaned Requirements

To enforce strict adherence to the baseline manifest and prevent typo errors (such as verifying `REQ-0001` instead of `REQ-001`), enable `--verifies-disallow-orphans`:

```bash
uv run pytest --verifies-baseline=requirements.json --verifies-disallow-orphans
```

If any test references a requirement ID absent from `requirements.json`, Pytest immediately halts during collection with an informative error listing the offending requirement ID and test location.
