# Standards Compliance

`pytest-verifies` assists engineering organisations in meeting rigorous software verification and traceability requirements across safety-critical and regulated domains.

---

## Mapped Engineering Standards

| Standard | Applicable Clauses | Compliance Support |
| :--- | :--- | :--- |
| **ISO 26262** *(Automotive Functional Safety)* | Part 6, Sections 9 & 10 | Establishes bidirectional requirement-to-test traceability for ASIL A–D software units, recording verifiable evidence of compliance. |
| **IEC 62304** *(Medical Device Software)* | Sections 5.7 & 5.8 | Automates verification testing documentation, failure diagnostics, and RTM generation for Class A, B, and C medical software. |
| **DO-178C** *(Airborne Systems)* | Section 6.4.4 | Demonstrates that high-level and low-level software requirements are verified through automated testing with objective records. |
| **SOC2 / ISO 27001** *(Information Security)* | CC7.1, CC7.4 | Auditable proof that automated security controls and regression tests verify baseline control specifications. |

---

## Audit-Ready Evidence

Each verification record captured by `pytest-verifies` includes:

* **Source Traceability:** Relative file path and exact line number of the verification block (`tests/test_pwr.py:42`).
* **Environmental Fingerprint:** Execution run ID, Git commit SHA, Git dirty state, hostname, timestamp (ISO-8601 UTC), Python version, and Pytest version.
* **Objective Telemetry:** Structured JSON data attached during test execution (`evidence={...}`).
* **Deterministic Status:** Unambiguous `PASS`, `PARTIAL`, or `FAIL` classification.
