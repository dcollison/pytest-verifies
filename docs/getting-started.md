# Getting Started

## Installation

Install using `uv` (recommended):

```bash
uv add pytest-verifies
```

Or using standard Python package managers:

```bash
pip install pytest-verifies
```

---

## 5-Minute Walkthrough

### 1. Declare Baseline Requirements

Create a requirements manifest `requirements.json` (or `.csv` / `.yaml`):

```json
{
  "requirements": [
    {
      "id": "REQ-AUTH-001",
      "text": "Users must provide a valid JWT bearer token"
    },
    {
      "id": "REQ-RATE-001",
      "text": "Rate limit API requests to 100 requests per minute"
    }
  ]
}
```

### 2. Annotate Your Pytest Tests

In `tests/test_auth.py`:

```python
from pytest_verifies import verifies


@verifies("REQ-AUTH-001")
def test_jwt_authentication():
    token = {"sub": "user_123", "active": True}
    assert token["active"] is True


def test_rate_limiter():
    with verifies("REQ-RATE-001"):
        request_count = 45
        assert request_count <= 100
```

### 3. Run Pytest with Report Generation

```bash
uv run pytest \
  --verifies-baseline=requirements.json \
  --verifies-md=rtm.md \
  --verifies-html=rtm.html \
  --verifies-json=rtm.json \
  --color=yes
```

Pytest prints an RTM scorecard directly in the console and writes the requested report artefacts.
