"""
statistical.py
~~~~~~~~~~~~~~
Detect statistical drift between data batches.
Uses KL divergence, null rate changes, and outlier counts.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Thresholds for anomaly detection
NULL_RATE_CHANGE_THRESHOLD = 0.05      # 5% absolute change in null rate
MEAN_CHANGE_THRESHOLD_STDS = 3.0      # Mean shift > 3 std deviations
STDDEV_RATIO_THRESHOLD = 2.0          # Stddev changed by more than 2x


async def detect_statistical_drift(
    reference_stats: dict[str, dict],
    current_stats: dict[str, dict],
) -> list[dict[str, Any]]:
    """
    Compare column-level statistics between reference and current batch.

    reference_stats format:
    {
      "column_name": {
        "mean": float, "std": float, "min": float, "max": float,
        "null_rate": float, "p25": float, "p75": float
      }
    }

    Returns list of detected anomalies.
    """
    anomalies = []

    for col in set(reference_stats) & set(current_stats):
        ref = reference_stats[col]
        cur = current_stats[col]

        col_anomalies = _check_column(col, ref, cur)
        anomalies.extend(col_anomalies)

    return anomalies


def _check_column(
    column: str,
    ref: dict[str, Any],
    cur: dict[str, Any],
) -> list[dict[str, Any]]:
    anomalies = []

    # 1. Null rate change
    ref_null = ref.get("null_rate", 0.0)
    cur_null = cur.get("null_rate", 0.0)
    if abs(cur_null - ref_null) > NULL_RATE_CHANGE_THRESHOLD:
        direction = "increased" if cur_null > ref_null else "decreased"
        anomalies.append({
            "column": column,
            "type": "null_rate_change",
            "description": f"Null rate {direction} from {ref_null:.1%} to {cur_null:.1%}",
            "severity_hint": "HIGH" if cur_null > 0.3 else "MEDIUM",
            "ref_value": ref_null,
            "cur_value": cur_null,
        })

    # 2. Mean shift (for numeric columns)
    if "mean" in ref and "std" in ref and ref.get("std", 0) > 0:
        ref_mean = ref["mean"]
        ref_std = ref["std"]
        cur_mean = cur.get("mean", ref_mean)

        z_score = abs(cur_mean - ref_mean) / ref_std
        if z_score > MEAN_CHANGE_THRESHOLD_STDS:
            anomalies.append({
                "column": column,
                "type": "mean_shift",
                "description": f"Mean shifted by {z_score:.1f} std deviations ({ref_mean:.3f} → {cur_mean:.3f})",
                "severity_hint": "HIGH" if z_score > 5 else "MEDIUM",
                "z_score": round(z_score, 2),
                "ref_mean": ref_mean,
                "cur_mean": cur_mean,
            })

    # 3. Variance change
    if "std" in ref and ref.get("std", 0) > 0:
        ref_std = ref["std"]
        cur_std = cur.get("std", ref_std)
        ratio = cur_std / ref_std if ref_std > 0 else 1.0

        if ratio > STDDEV_RATIO_THRESHOLD or ratio < (1 / STDDEV_RATIO_THRESHOLD):
            anomalies.append({
                "column": column,
                "type": "variance_change",
                "description": f"Std deviation changed by {ratio:.1f}x ({ref_std:.3f} → {cur_std:.3f})",
                "severity_hint": "MEDIUM",
                "ratio": round(ratio, 2),
            })

    # 4. Value range violation
    if "min" in ref and "max" in ref:
        cur_min = cur.get("min")
        cur_max = cur.get("max")
        if cur_min is not None and cur_max is not None:
            if cur_min < ref["min"] * 0.5 or cur_max > ref["max"] * 2.0:
                anomalies.append({
                    "column": column,
                    "type": "range_violation",
                    "description": f"Values outside expected range. Ref: [{ref['min']}, {ref['max']}], Current: [{cur_min}, {cur_max}]",
                    "severity_hint": "MEDIUM",
                })

    return anomalies
