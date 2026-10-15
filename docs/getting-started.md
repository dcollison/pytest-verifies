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
      "id": "REQ-PWR-001",
      "title": "Nominal Power Rail",
      "priority": "HIGH"
    },
    {
      "id": "REQ-SAF-001",
      "title": "Thermal Cutoff Guard",
      "priority": "CRITICAL"
    }
  ]
}
```

### 2. Annotate Your Pytest Tests

In `tests/test_power.py`:

```python
from pytest_verifies import verifies

@verifies("REQ-PWR-001")
def test_power_rail():
    voltage = 5.0
    assert voltage == 5.0

def test_thermal_guard():
    with verifies("REQ-SAF-001"):
        temp_c = 45.0
        assert temp_c < 85.0
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
