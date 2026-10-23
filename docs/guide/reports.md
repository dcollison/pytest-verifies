# Reports & Quality Gates

`pytest-verifies` outputs multiple artefact formats suitable for enterprise PLM/ALM tools, CI summaries, and compliance audits.

---

## Output Formats

### 1. Interactive Single-File HTML5 (`--verifies-html=rtm.html`)
* **Zero External Dependencies:** Built entirely with inline CSS and vanilla JavaScript. Functions offline and in air-gapped environments.
* **Top Metric Cards:** Instant view of Pass %, Fail %, Partial %, and Orphan counts.
* **Live Search & Filter:** Filter by status (`All`, `Pass`, `Partial`, `Fail`, `Orphans`) or live search by requirement ID, title, test name, or source file.
* **Diagnostic Expansion:** Collapsible `<details>` blocks show exact test source locations (`tests/test_pwr.py:42`), duration, failure diffs, and structured JSON telemetry.

### 2. GitHub / GitLab Markdown Summary (`--verifies-md=rtm.md`)
* Formatted directly for `$GITHUB_STEP_SUMMARY` and merge request comments.
* Contains a summary scorecard table, requirements traceability table, and collapsible diagnostics.
* Free of informal emojis for clean, corporate-ready PR feedback.

### 3. Structured JSON (`--verifies-json=rtm.json`)
* Full machine-readable data model containing run metadata (Git SHA, dirty status, hostname, timestamps, Python/Pytest versions) and granular verification records.
* Ideal for programmatic ingestion into corporate databases or custom dashboards.

### 4. Tabular CSV (`--verifies-csv=rtm.csv`)
* Flat schema suitable for enterprise tools (Jira, Jama Connect, Polarion ALM):
```csv
req_id,text,status,in_baseline,stages,tests,evidence,failure_messages
```
*(The `stages` column is dynamically included only when execution stages are configured).*

---

## Quality Gates

* **Coverage Gate (`--verifies-fail-under=FLOAT`):** Halts session with exit code `1` if verified requirement coverage % is below threshold.
* **Zero Defects:** Halts session with exit code `1` if any requirement resolved to `FAIL` (or recorded failure diagnostics).
* **Orphan Gate (`--verifies-disallow-orphans`):** Halts collection/session if untracked requirement IDs are detected.
