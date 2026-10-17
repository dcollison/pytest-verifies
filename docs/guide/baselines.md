# Baseline Requirement Manifests

A baseline manifest establishes the master list of requirements that automated tests must verify.

---

## Supported Formats

Baseline manifests require only an `id` and a requirement statement `text` (or `description`).

### 1. JSON (`requirements.json`)

Supports array format or top-level dictionary:

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

Or as a compact dictionary:

```json
{
  "REQ-DOG-001": "Dogs must be able to bark",
  "REQ-CAT-001": "Cats must be able to purr when content"
}
```

### 2. CSV (`requirements.csv`)

Requires an `id` column header (case-insensitive), paired with `text` (or `description`):

```csv
id,text
REQ-DOG-001,Dogs must be able to bark
REQ-CAT-001,Cats must be able to purr when content
```

### 3. YAML (`requirements.yaml`)

Requires `pyyaml` (installed automatically if using `docs` or `dev` dependency groups):

```yaml
requirements:
  - id: REQ-DOG-001
    text: Dogs must be able to bark
  - id: REQ-CAT-001
    text: Cats must be able to purr when content
```

---

## Disallowing Orphaned Requirements

To enforce strict adherence to the baseline manifest and prevent typo errors (such as verifying `REQ-0001` instead of `REQ-001`), enable `--verifies-disallow-orphans`:

```bash
uv run pytest --verifies-baseline=requirements.json --verifies-disallow-orphans
```

If any test references a requirement ID absent from `requirements.json`, Pytest immediately halts during collection with an informative error listing the offending requirement ID and test location.
