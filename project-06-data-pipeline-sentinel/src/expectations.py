"""
expectations.py
~~~~~~~~~~~~~~~
Auto-generate and update Great Expectations suites based on detected schema changes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GX_SUITES_DIR = Path("gx_suites")


async def update_expectation_suite(source: str, schema_diff: dict[str, Any]) -> None:
    """
    Update the Great Expectations suite for a data source based on detected schema changes.
    Adds expectations for new columns, removes expectations for deleted columns.
    """
    GX_SUITES_DIR.mkdir(exist_ok=True)
    suite_path = GX_SUITES_DIR / f"{source}.json"

    # Load existing suite or create new one
    if suite_path.exists():
        with open(suite_path) as f:
            suite = json.load(f)
    else:
        suite = {
            "data_asset_type": None,
            "expectation_suite_name": source,
            "expectations": [],
            "ge_cloud_id": None,
        }

    expectations = suite.get("expectations", [])

    # Remove expectations for deleted columns
    for removed_col in schema_diff.get("removed_columns", []):
        expectations = [
            e for e in expectations
            if e.get("kwargs", {}).get("column") != removed_col
        ]
        logger.info("Removed expectations for dropped column: %s", removed_col)

    # Add expectations for new columns
    for new_col in schema_diff.get("new_columns", []):
        # Basic: column exists
        new_expectation = {
            "expectation_type": "expect_column_to_exist",
            "kwargs": {"column": new_col},
            "meta": {"added_by": "sentinel_agent", "auto_generated": True},
        }
        # Avoid duplicates
        existing_types = {
            (e["expectation_type"], e.get("kwargs", {}).get("column"))
            for e in expectations
        }
        if ("expect_column_to_exist", new_col) not in existing_types:
            expectations.append(new_expectation)
            logger.info("Added expect_column_to_exist for: %s", new_col)

    # Handle type changes
    for type_change in schema_diff.get("type_changes", []):
        col = type_change["column"]
        new_dtype = type_change["new_dtype"]

        # Update or add type expectation
        type_map = {
            "int64": "int", "int32": "int", "float64": "float",
            "float32": "float", "object": "str", "bool": "bool",
        }
        gx_type = type_map.get(new_dtype, new_dtype)

        # Remove old type expectation
        expectations = [
            e for e in expectations
            if not (
                e["expectation_type"] == "expect_column_values_to_be_of_type"
                and e.get("kwargs", {}).get("column") == col
            )
        ]
        # Add new one
        expectations.append({
            "expectation_type": "expect_column_values_to_be_of_type",
            "kwargs": {"column": col, "type_": gx_type},
            "meta": {"updated_by": "sentinel_agent", "auto_generated": True},
        })

    suite["expectations"] = expectations

    with open(suite_path, "w") as f:
        json.dump(suite, f, indent=2)

    logger.info("Updated GX suite for %s: %d expectations", source, len(expectations))


def generate_column_expectations(column: str, stats: dict[str, Any]) -> list[dict]:
    """Generate data quality expectations from observed column statistics."""
    expectations = []

    # Always: column exists
    expectations.append({
        "expectation_type": "expect_column_to_exist",
        "kwargs": {"column": column},
    })

    # Null rate
    null_rate = stats.get("null_rate", 0.0)
    if null_rate < 0.01:
        expectations.append({
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": column},
            "meta": {"observed_null_rate": null_rate},
        })

    # Value range for numerics
    if "min" in stats and "max" in stats:
        expectations.append({
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column": column,
                "min_value": stats["min"],
                "max_value": stats["max"],
                "mostly": 0.99,
            },
        })

    return expectations
