# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - 2026-10-23

### Changed
- Standardized step identifier parameter on `step_id` across `verifies(...)` and `_VerifiesContext`, eliminating the redundant `step` alias.
- Standardized pytest marker registration and extraction on `step_id`.

## [1.1.1] - 2026-10-23

### Added
- First-class support for discrete test procedure step IDs (`STEP-01`, `1.1`) and action steps via `step(...)` context manager.
- Support for `step` parameter in `verifies(..., step="...")` context manager and decorator.
- Action step telemetry and status tracking in consolidated RTM artefacts and reports.

### Changed
- Changed status nomenclature from `VERIFIED` and `UNVERIFIED` to `PASS` and `FAIL` across data models, console output, and all exported report formats (HTML, Markdown, CSV, JSON).
- Fixed console summary table column alignment when displaying orphaned requirements (`[ORPHAN]`).
- Conditionally omit the `Stages` column across all RTM report formats unless execution stages are explicitly configured.
- Improved partial verification resolution: when multiple tests verify the same requirement and yield mixed outcomes (e.g. one pass and one fail), the requirement now resolves to `PARTIAL` rather than unconditionally falling back to `FAIL`.
- Simplified baseline requirement manifest schema to `id` and requirement `text`/`description`.
- Hardened lifecycle hooks and test execution teardown handling.
- Enhanced static typing across all plugin modules and integrated `types-pyyaml` stubs.

## [0.0.1] - 2026-10-23

### Added
- Initial release of `pytest-verifies`, an enterprise requirements traceability plugin for pytest.
- Unified `verifies(...)` API functioning as a decorator, context manager, and test parameter mark (`pytest.param(..., marks=verifies(...))`).
- Native `assert` statement support preserving Pytest's AST rewriting and rich diff diagnostics.
- Soft assertions (`soft=True` or `--verifies-soft`) for non-fatal requirement verification within tests.
- Dynamic objective runtime evidence capture via `ctx.attach(key, value)` and `ctx.record_evidence(dict)`.
- Baseline requirement manifest ingestion supporting JSON, CSV, and YAML formats (`--verifies-baseline`).
- Concurrency-safe execution with `pytest-xdist` using IPC via `report.user_properties`.
- Multi-run shard consolidation via CLI (`pytest-verifies combine`).
- Multi-format report generation:
  - Interactive single-file HTML5 report with zero external CDN/network dependencies.
  - GitHub / GitLab step summary Markdown report.
  - Tabular CSV export for enterprise ALM/PLM tools.
  - Structured JSON Requirements Traceability Matrix (RTM).
- Strict quality gates: `--verifies-fail-under` (coverage threshold) and `--verifies-disallow-orphans` (orphaned ID prevention).
- Requirement filtering at test execution time via `--req="PATTERN"`.
