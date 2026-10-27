# Assertions, Contexts & Evidence

## Overview

`pytest-verifies` relies strictly on native Python `assert` statements. This ensures full compatibility with Pytest's AST rewriting, providing rich assertion diffs without introducing proprietary assertion wrappers.

---

## 1. Function and Class Decorators

Use `@verifies(...)` on test functions or test classes:

```python
from pytest_verifies import verifies


@verifies("REQ-DOG-001", "REQ-DOG-002", description="Golden retrievers are friendly dogs")
def test_retriever_temperament():
    dog = {"breed": "Golden Retriever", "friendly": True}
    assert dog["friendly"] is True
```

When decorating a test class, all test methods within the class automatically inherit verification tracking for the specified requirements:

```python
@verifies("REQ-CAT-001")
class TestCatAgility:
    def test_land_on_feet(self):
        cat = {"lands_on_feet": True}
        assert cat["lands_on_feet"] is True

    def test_silent_stalking(self):
        cat = {"stealthy": True}
        assert cat["stealthy"] is True
```

---

## 2. Context Manager

Use `with verifies(...)` for statement-level or multi-block verification:

```python
from pytest_verifies import verifies


def test_dog_and_cat_habits():
    # Single-line check
    with verifies("REQ-DOG-001"):
        assert "bark" != "meow"

    # Multi-statement block
    with verifies("REQ-CAT-002", description="Cats take multiple naps per day"):
        nap_count = 5
        assert nap_count >= 3
```

---

## 3. Soft Assertions

In standard Pytest execution, the first failed assertion aborts the test function. In verification testing, it is often desirable to check several independent qualities within a single test without aborting after the first failure.

Enable soft assertions per block with `soft=True`, or globally across all blocks with `--verifies-soft`:

```python
from pytest_verifies import verifies


def test_cat_qualities():
    cat = {"is_napping": True, "purr_volume_db": 45, "caught_laser": False}

    # Block 1 fails softly; execution continues!
    with verifies("REQ-CAT-001", soft=True):
        assert cat["caught_laser"] is True, "The red dot eluded the cat once again!"

    # Block 2 executes and records PASS
    with verifies("REQ-CAT-002", soft=True):
        assert cat["is_napping"] is True

    # At the end of test_cat_qualities, Pytest consolidates failures and fails the test.
```

---

## 4. Objective Evidence Attachment

Audit frameworks require verifiable proof of test outcomes. Objective evidence can be provided statically or dynamically:

```python
from pytest_verifies import verifies


def test_dog_fetch_telemetry():
    # Static evidence dictionary
    with verifies("REQ-DOG-001", evidence={"breed": "Labrador", "good_boy": True}):
        assert True

    # Dynamic attachment during runtime
    with verifies("REQ-DOG-002") as ctx:
        balls_fetched = 7
        ctx.attach("balls_fetched", balls_fetched)
        ctx.record_evidence({"tail_wagging": True})
        assert balls_fetched >= 5
```

---

## 5. Test Procedure Steps & Action Steps

Test specifications often define explicit **Step IDs** (e.g. `STEP-01`, `1.1`), which fall into two categories:

1. **Action Steps (Setup / Preparation):** Perform setup or state changes without directly validating a requirement.
2. **Verification Steps:** Directly assert behaviour against one or more requirements.

Import `step` alongside `verifies`:

```python
from pytest_verifies import step, verifies


def test_puppy_training_routine():
    # 1. Action Step: Prepare treats and call puppy
    with step("STEP-01", description="Fill treat pouch and call puppy"):
        puppy = {"name": "Buster", "tricks": []}

    # 2. Action Step with Telemetry Evidence
    with step("STEP-02", description="Offer treat to puppy") as s:
        puppy["tricks"].append("sit")
        s.attach("treats_given", 1)

    # 3. Verification Step using step(..., verifies=...)
    with step(
        "STEP-03",
        description="Verify puppy sits on command",
        verifies="REQ-DOG-003",
    ):
        assert "sit" in puppy["tricks"]

    # 4. Verification Step using verifies(..., step_id=...)
    with verifies(
        "REQ-DOG-002", step_id="STEP-04", description="Verify puppy wags tail when praised"
    ):
        puppy_happy = True
        assert puppy_happy is True
```

### Benefits of Step Tracking
* **Failure Attribution:** If an action step fails (e.g. dropped the bowl during `STEP-01`), the failure report clearly attributes the issue to the action step without falsely recording requirement defects.
* **Audit Trail:** Reports include a complete test procedure walkthrough table matching your formal verification protocol.
* **Traceability Export:** Step IDs export directly to the `steps` column in CSV and JSON for external reporting tools.
