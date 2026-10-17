# Assertions, Contexts & Evidence

## Overview

`pytest-verifies` relies strictly on native Python `assert` statements. This ensures full compatibility with Pytest's AST rewriting, providing rich assertion diffs without introducing proprietary assertion wrappers.

---

## 1. Function and Class Decorators

Use `@verifies(...)` on test functions or test classes:

```python
from pytest_verifies import verifies


@verifies("REQ-AUTH-001", "REQ-AUTH-002", description="Authentication service init")
def test_auth_service_init():
    assert True
```

When decorating a test class, all test methods within the class automatically inherit verification tracking for the specified requirements:

```python
@verifies("REQ-USER-001")
class TestUserService:
    def test_create_user(self):
        assert True

    def test_delete_user(self):
        assert True
```

---

## 2. Context Manager

Use `with verifies(...)` for statement-level or multi-block verification:

```python
from pytest_verifies import verifies


def test_jwt_claims():
    # Single-line check
    with verifies("REQ-AUTH-001"):
        assert 1 == 1

    # Multi-statement block
    with verifies("REQ-AUTH-002", description="Payload signature validation"):
        issuer = "https://auth.example.com"
        token = {"iss": issuer, "exp": 1893456000}
        assert token["iss"] == issuer
```

---

## 3. Soft Assertions

In standard Pytest execution, the first failed assertion aborts the test function. In software testing, it is often desirable to check several independent validations within a single test without aborting after the first failure.

Enable soft assertions per block with `soft=True`, or globally across all blocks with `--verifies-soft`:

```python
from pytest_verifies import verifies


def test_user_profile_validation():
    # Block 1 fails softly; execution continues!
    with verifies("REQ-VAL-001", soft=True):
        assert 10 > 20, "Age below required threshold"

    # Block 2 executes and records VERIFIED
    with verifies("REQ-VAL-002", soft=True):
        assert "user@example.com".endswith(".com")

    # At the end of test_user_profile_validation, Pytest consolidates failures and fails the test.
```

---

## 4. Objective Evidence Attachment

Audit frameworks require verifiable proof of test outcomes. Objective evidence can be provided statically or dynamically:

```python
from pytest_verifies import verifies


def test_payment_processing():
    # Static evidence dictionary
    with verifies("REQ-PAY-001", evidence={"gateway": "Stripe", "currency": "GBP"}):
        assert True

    # Dynamic attachment during runtime
    with verifies("REQ-PAY-002") as ctx:
        latency_ms = 45.2
        ctx.attach("latency_ms", latency_ms)
        ctx.record_evidence({"idempotency_key": "idem_123456"})
        assert latency_ms < 100.0
```

---

## 5. Test Procedure Steps & Action Steps

In formal test protocols (such as enterprise verification, SOC2, or regulated software delivery), test specifications define explicit **Step IDs** (e.g. `STEP-01`, `1.1`). These steps fall into two categories:

1. **Action Steps (Setup / Operation):** Perform state transitions, database seeding, or API calls without directly validating a requirement.
2. **Verification Steps:** Directly assert system behaviour against one or more requirements.

Import `step` alongside `verifies`:

```python
from pytest_verifies import step, verifies


def test_user_checkout_journey():
    # 1. Pure Action Step: No requirement verified
    with step("STEP-01", description="Seed customer and inventory records"):
        db.seed_customer("user_123")
        db.seed_product("prod_456", stock=10)

    # 2. Action Step with Telemetry Evidence
    with step("STEP-02", description="Apply discount code to cart") as s:
        discount = cart.apply_coupon("SAVE20")
        s.attach("discount_percentage", discount.pct)

    # 3. Verification Step using step(..., verifies=...)
    with step(
        "STEP-03", description="Verify discounted total calculation", verifies="REQ-CART-004"
    ):
        assert cart.total_gbp == 80.0

    # 4. Verification Step using verifies(..., step=...)
    with verifies("REQ-PAY-005", step="STEP-04", description="Verify payment confirmation webhook"):
        assert webhook.delivered is True
```

### Benefits of Step Tracking
* **Failure Attribution:** If an action step fails (e.g. database timeout during `STEP-01`), the failure report clearly attributes the issue to the action step without falsely recording requirement defects.
* **Audit Trail:** Reports include a complete test procedure walkthrough table matching your formal verification protocol.
* **ALM / PLM Synchronization:** Step IDs export directly to the `steps` column in CSV and JSON for tools like Polarion, Jira Xray, and Jama.
