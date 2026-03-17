"""
schema_diff.py
~~~~~~~~~~~~~~
Compare two data schemas and detect structural changes.
"""

from __future__ import annotations

from typing import Any


async def compute_schema_diff(
    reference_schema: dict[str, str],
    current_schema: dict[str, str],
) -> dict[str, Any]:
    """
    Compare two schemas (column_name → dtype mappings) and return a diff.

    Args:
        reference_schema: {"col1": "int64", "col2": "object", ...}
        current_schema: Same format but for the current batch

    Returns:
        {"changes": [...], "has_breaking_changes": bool, "summary": str}
    """
    changes = []

    # New columns
    for col in set(current_schema) - set(reference_schema):
        changes.append({
            "type": "new_column",
            "column": col,
            "dtype": current_schema[col],
            "description": f"New column '{col}' ({current_schema[col]}) not in reference",
            "breaking": False,
        })

    # Removed columns
    for col in set(reference_schema) - set(current_schema):
        changes.append({
            "type": "removed_column",
            "column": col,
            "dtype": reference_schema[col],
            "description": f"Column '{col}' removed from data source",
            "breaking": True,
        })

    # Type changes
    for col in set(reference_schema) & set(current_schema):
        if reference_schema[col] != current_schema[col]:
            old_type = reference_schema[col]
            new_type = current_schema[col]
            # Type widening (int → float) is non-breaking; narrowing or str→numeric is breaking
            breaking = _is_breaking_type_change(old_type, new_type)
            changes.append({
                "type": "type_change",
                "column": col,
                "old_dtype": old_type,
                "new_dtype": new_type,
                "description": f"Column '{col}' type changed: {old_type} → {new_type}",
                "breaking": breaking,
            })

    has_breaking = any(c["breaking"] for c in changes)
    summary = f"{len(changes)} schema changes detected" + (" (BREAKING)" if has_breaking else "") if changes else "No schema changes"

    return {
        "changes": changes,
        "has_breaking_changes": has_breaking,
        "new_columns": [c["column"] for c in changes if c["type"] == "new_column"],
        "removed_columns": [c["column"] for c in changes if c["type"] == "removed_column"],
        "type_changes": [c for c in changes if c["type"] == "type_change"],
        "summary": summary,
    }


def _is_breaking_type_change(old_type: str, new_type: str) -> bool:
    safe_widenings = {
        ("int32", "int64"), ("int64", "float64"),
        ("float32", "float64"), ("int32", "float64"),
    }
    return (old_type, new_type) not in safe_widenings
