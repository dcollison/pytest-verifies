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
      "id": "REQ-FRUIT-001",
      "text": "Apples must be crisp and sweet"
    },
    {
      "id": "REQ-ANIMAL-001",
      "text": "Dogs must wag their tails when happy"
    }
  ]
}
```

### 2. Annotate Your Pytest Tests

In `tests/test_orchard.py`:

```python
from pytest_verifies import verifies


@verifies("REQ-FRUIT-001")
def test_apple_crispness():
    apple = {"variety": "Honeycrisp", "crisp": True}
    assert apple["crisp"] is True


def test_happy_dog():
    with verifies("REQ-ANIMAL-001"):
        dog = {"name": "Buster", "tail_wagging": True}
        assert dog["tail_wagging"] is True
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
