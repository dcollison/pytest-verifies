# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-10-23

### Added
- Initial release of `pytest-verifies`, an enterprise requirements traceability plugin for pytest.
- Unified `verifies(...)` API functioning as a decorator, context manager, and test parameter mark (`pytest.param(..., marks=verifies(...))`).
- Native `assert` statement support preserving Pytest's AST rewriting and rich diff diagnostics.
- Soft assertions (`soft=True` or `--verifies-soft`) for non-fatal requirement verification within tests.
- Dynamic objective runtime evidence capture via `ctx.attach(key, value)` and `ctx.record_evidence(dict)`.
- First-class test procedure step IDs and action steps via `step(...)` and `verifies(..., step=...)`.
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
