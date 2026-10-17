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
@verifies("REQ-DUCK-001")
class TestDuckBehaviour:
    def test_quack(self):
        assert "quack" == "quack"

    def test_waddle(self):
        assert True
```

---

## 2. Context Manager

Use `with verifies(...)` for statement-level or multi-block verification:

```python
from pytest_verifies import verifies


def test_fruit_basket():
    # Single-line check
    with verifies("REQ-FRUIT-001"):
        assert "banana" != "orange"

    # Multi-statement block
    with verifies("REQ-FRUIT-002", description="Lemons must be appropriately sour"):
        lemon_sourness = 9
        assert lemon_sourness > 5
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

    # Block 2 executes and records VERIFIED
    with verifies("REQ-CAT-002", soft=True):
        assert cat["is_napping"] is True

    # At the end of test_cat_qualities, Pytest consolidates failures and fails the test.
```

---

## 4. Objective Evidence Attachment

Audit frameworks require verifiable proof of test outcomes. Objective evidence can be provided statically or dynamically:

```python
from pytest_verifies import verifies


def test_zoo_snack_time():
    # Static evidence dictionary
    with verifies("REQ-PANDA-001", evidence={"favourite_food": "bamboo", "eaten_kg": 12}):
        assert True

    # Dynamic attachment during runtime
    with verifies("REQ-MONKEY-001") as ctx:
        bananas_eaten = 5
        ctx.attach("bananas_eaten", bananas_eaten)
        ctx.record_evidence({"snack_type": "ripe banana"})
        assert bananas_eaten >= 3
```

---

## 5. Test Procedure Steps & Action Steps

Test specifications often define explicit **Step IDs** (e.g. `STEP-01`, `1.1`), which fall into two categories:

1. **Action Steps (Setup / Preparation):** Prepare ingredients or configure state without directly validating a requirement.
2. **Verification Steps:** Directly assert behaviour against one or more requirements.

Import `step` alongside `verifies`:

```python
from pytest_verifies import step, verifies


def test_fruit_salad_recipe():
    # 1. Action Step: Prepare ingredients without verifying a requirement
    with step("STEP-01", description="Chop watermelon and peel bananas"):
        salad_bowl = ["watermelon", "banana"]

    # 2. Action Step with Telemetry Evidence
    with step("STEP-02", description="Add fresh berries to bowl") as s:
        salad_bowl.extend(["strawberry", "blueberry"])
        s.attach("berry_count", 2)

    # 3. Verification Step using step(..., verifies=...)
    with step(
        "STEP-03",
        description="Verify fruit salad contains at least 3 fruits",
        verifies="REQ-SALAD-001",
    ):
        assert len(salad_bowl) >= 3

    # 4. Verification Step using verifies(..., step=...)
    with verifies("REQ-SALAD-002", step="STEP-04", description="Verify watermelon is in the bowl"):
        assert "watermelon" in salad_bowl
```

### Benefits of Step Tracking
* **Failure Attribution:** If an action step fails (e.g. dropped the bowl during `STEP-01`), the failure report clearly attributes the issue to the action step without falsely recording requirement defects.
* **Audit Trail:** Reports include a complete test procedure walkthrough table matching your formal verification protocol.
* **Traceability Export:** Step IDs export directly to the `steps` column in CSV and JSON for external reporting tools.
