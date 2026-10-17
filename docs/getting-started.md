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
      "id": "REQ-DOG-001",
      "text": "Dogs must wag their tails when happy"
    },
    {
      "id": "REQ-CAT-001",
      "text": "Cats must purr when content"
    }
  ]
}
```

### 2. Annotate Your Pytest Tests

In `tests/test_pets.py`:

```python
from pytest_verifies import verifies


@verifies("REQ-DOG-001")
def test_happy_dog():
    dog = {"name": "Buster", "tail_wagging": True}
    assert dog["tail_wagging"] is True


def test_content_cat():
    with verifies("REQ-CAT-001"):
        cat = {"name": "Whiskers", "purring": True}
        assert cat["purring"] is True
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
