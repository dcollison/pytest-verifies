"""pytest-verifies: Enterprise requirements traceability plugin for pytest.

Enables automated linking between test executions and formal engineering
requirements, producing comprehensive Requirements Traceability Matrix (RTM) artefacts.
"""

from __future__ import annotations

from pytest_verifies.context import step, verifies

__version__ = "1.1.1"

__all__ = ["step", "verifies", "__version__"]
