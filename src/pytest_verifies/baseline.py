"""Loader and validator for baseline requirement manifests.

Supports loading requirement manifests from JSON, CSV, and YAML formats with
comprehensive schema validation and consistent British English error reporting.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pytest_verifies.models import BaselineRequirement


def load_baseline(path: str | Path) -> dict[str, BaselineRequirement]:
    """Load and validate a baseline requirement manifest from disk.

    Args:
        path: Path to the requirement manifest file (.json, .csv, .yaml, or .yml).

    Returns:
        dict[str, BaselineRequirement]: Mapping of requirement ID to requirement details.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the file format is unsupported or the schema is invalid.
        RuntimeError: If PyYAML is required but not installed.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Baseline requirements manifest not found: '{manifest_path}'")

    suffix = manifest_path.suffix.lower()
    if suffix == ".json":
        return _load_json_baseline(manifest_path)
    elif suffix == ".csv":
        return _load_csv_baseline(manifest_path)
    elif suffix in (".yaml", ".yml"):
        return _load_yaml_baseline(manifest_path)
    else:
        raise ValueError(
            f"Unsupported baseline file format '{suffix}'. "
            "Supported formats are .json, .csv, and .yaml / .yml."
        )


def _load_json_baseline(path: Path) -> dict[str, BaselineRequirement]:
    """Load baseline requirements from a JSON file."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in baseline manifest '{path}': {exc}") from exc

    return _parse_baseline_data(data, path)


def _load_csv_baseline(path: Path) -> dict[str, BaselineRequirement]:
    """Load baseline requirements from a CSV file."""
    requirements: dict[str, BaselineRequirement] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "id" not in [
            name.strip().lower() for name in reader.fieldnames
        ]:
            raise ValueError(f"CSV baseline manifest '{path}' must contain an 'id' header column.")

        for line_no, row in enumerate(reader, start=2):
            if not any((v or "").strip() for k, v in row.items() if k and isinstance(v, str)):
                continue

            # Normalise keys to lowercase
            norm_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
            req_id = norm_row.get("id", "").strip()
            if not req_id:
                raise ValueError(
                    f"Line {line_no} in CSV baseline manifest '{path}' contains an empty requirement ID."
                )

            requirements[req_id] = BaselineRequirement.from_dict(norm_row)

    return requirements


def _load_yaml_baseline(path: Path) -> dict[str, BaselineRequirement]:
    """Load baseline requirements from a YAML file."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to parse YAML baseline files. Please install pyyaml."
        ) from exc

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise ValueError(f"Malformed YAML in baseline manifest '{path}': {exc}") from exc

    return _parse_baseline_data(data, path)


def _parse_baseline_data(data: Any, path: Path) -> dict[str, BaselineRequirement]:
    """Parse dictionary or list data structures into a validated requirement mapping."""
    requirements: dict[str, BaselineRequirement] = {}

    if isinstance(data, dict):
        if "requirements" in data and isinstance(data["requirements"], list):
            items = data["requirements"]
            for idx, item in enumerate(items):
                if (
                    not isinstance(item, dict)
                    or item.get("id") is None
                    or not str(item["id"]).strip()
                ):
                    raise ValueError(
                        f"Item {idx} in 'requirements' list of '{path}' must be a dictionary with an 'id'."
                    )
                req = BaselineRequirement.from_dict(item)
                requirements[req.id] = req
        else:
            # Format: {"REQ-1": {"title": "..."}, "REQ-2": {...}}
            for key, val in data.items():
                req_id = str(key).strip() if key is not None else ""
                if not req_id:
                    raise ValueError(
                        f"Baseline manifest '{path}' contains an empty requirement ID."
                    )
                if isinstance(val, dict):
                    item_dict = dict(val)
                    if item_dict.get("id") is None or not str(item_dict["id"]).strip():
                        item_dict["id"] = req_id
                    req = BaselineRequirement.from_dict(item_dict)
                elif val is None:
                    req = BaselineRequirement(id=req_id, text="")
                else:
                    # Could be scalar description: {"REQ-1": "Requirement text"}
                    req = BaselineRequirement(id=req_id, text=str(val).strip())
                requirements[req.id] = req

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            if not isinstance(item, dict) or item.get("id") is None or not str(item["id"]).strip():
                raise ValueError(
                    f"Item {idx} in '{path}' must be a dictionary containing a non-empty 'id'."
                )
            req = BaselineRequirement.from_dict(item)
            requirements[req.id] = req
    else:
        raise ValueError(
            f"Unexpected data format in baseline manifest '{path}'. Expected dict or list."
        )

    return requirements
