# Baseline Requirement Manifests

A baseline manifest establishes the master list of requirements that automated tests must verify.

---

## Supported Formats

Baseline manifests require only an `id` and a requirement statement `text`. For compatibility with various external systems and legacy CSV exports, `text`, `description`, `title`, and `requirement` are accepted interchangeably as the requirement statement.

### 1. JSON (`requirements.json`)

Supports array format or top-level dictionary:

```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "text": "Trigger shutdown if current exceeds 2.0 A"
    },
    {
      "id": "REQ-002",
      "text": "Watchdog periodic heartbeat timer within 500 ms"
    }
  ]
}
```

Or as a compact dictionary:

```json
{
  "REQ-001": "Trigger shutdown if current exceeds 2.0 A",
  "REQ-002": "Watchdog periodic heartbeat timer within 500 ms"
}
```

### 2. CSV (`requirements.csv`)

Requires an `id` column header (case-insensitive), paired with `text` (or `description` / `title` / `requirement`):

```csv
id,text
REQ-001,Trigger shutdown if current exceeds 2.0 A
REQ-002,Watchdog periodic heartbeat timer within 500 ms
```

### 3. YAML (`requirements.yaml`)

Requires `pyyaml` (installed automatically if using `docs` or `dev` dependency groups):

```yaml
requirements:
  - id: REQ-001
    text: Trigger shutdown if current exceeds 2.0 A
  - id: REQ-002
    text: Watchdog periodic heartbeat timer within 500 ms
```

---

## Disallowing Orphaned Requirements

To enforce strict adherence to the baseline manifest and prevent typo errors (such as verifying `REQ-0001` instead of `REQ-001`), enable `--verifies-disallow-orphans`:

```bash
uv run pytest --verifies-baseline=requirements.json --verifies-disallow-orphans
```

If any test references a requirement ID absent from `requirements.json`, Pytest immediately halts during collection with an informative error listing the offending requirement ID and test location.
