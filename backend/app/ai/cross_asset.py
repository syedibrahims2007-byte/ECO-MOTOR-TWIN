"""Cross-asset intelligence — suppress false alarms using process relationships.

Key idea from report Section 12:
Before raising a motor-specific alert, check whether other motors and
cell production explain the deviation. If M2 current is up but M1 speed
and production are also up, classify as process load change (suppress).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def check_process_load_explanation(
    motor_id: str,
    motor_reading: dict[str, Any],
    all_readings: dict[str, dict[str, Any]],
    process_chain: list[dict[str, Any]],
    nominals: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check if a motor's deviation is explained by process load changes.

    Args:
        nominals: optional ``{motor_id: {"current_a": ...}}`` reference values.
            When provided, an upstream motor counts as "increased" only if its
            current exceeds nominal by more than 5%. Without nominals the
            legacy heuristic (upstream readings present) is used.

    Returns:
        dict with keys:
        - is_explained: bool — True if process load explains the deviation
        - reason: str — explanation
        - related_motors: list[str] — motors that explain the deviation
    """
    result = {
        "is_explained": False,
        "reason": "",
        "related_motors": [],
    }

    # Find upstream motors in the process chain
    upstream = []
    for link in process_chain:
        if link["to"] == motor_id:
            upstream.append(link["from"])

    if not upstream:
        return result

    upstream_increased = []
    for up_id in upstream:
        if up_id not in all_readings:
            continue
        up_reading = all_readings[up_id]
        up_current = up_reading.get("Current_A", 0)

        if nominals and up_id in nominals:
            nom_current = nominals[up_id].get("current_a", 0)
            # Upstream is working harder than nominal → process load increase
            if nom_current > 0 and up_current > nom_current * 1.05:
                upstream_increased.append(up_id)
        else:
            # Legacy heuristic: upstream readings present at all
            if up_reading.get("RPM", 0) > 0 and up_current > 0:
                upstream_increased.append(up_id)

    if upstream_increased:
        result["is_explained"] = True
        result["reason"] = (
            f"Process load change: upstream motor(s) {', '.join(upstream_increased)} "
            f"show increased load, explaining {motor_id} deviation"
        )
        result["related_motors"] = upstream_increased

    return result


def should_suppress_alert(
    motor_id: str,
    anomaly_score: float,
    all_readings: dict[str, dict[str, Any]],
    process_chain: list[dict[str, Any]],
    cell_production: float,
    base_production: float,
    nominals: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Determine if an alert should be suppressed or downgraded.

    Returns:
        dict with:
        - suppress: bool — True if alert should be suppressed
        - downgrade: bool — True if severity should be reduced
        - reason: str — reasoning
        - category: str — alert category (e.g., "process_load_change")
    """
    result = {
        "suppress": False,
        "downgrade": False,
        "reason": "",
        "category": "motor_fault",
    }

    if motor_id not in all_readings:
        return result

    motor_reading = all_readings[motor_id]

    # Check if cell production is elevated (process running harder)
    production_ratio = cell_production / base_production if base_production > 0 else 1.0

    # Check upstream explanation
    explanation = check_process_load_explanation(
        motor_id, motor_reading, all_readings, process_chain, nominals=nominals
    )

    if explanation["is_explained"] and production_ratio > 1.1:
        result["suppress"] = True
        result["reason"] = explanation["reason"]
        result["category"] = "process_load_change"
        logger.info("Alert suppressed for %s: %s", motor_id, explanation["reason"])
    elif explanation["is_explained"]:
        result["downgrade"] = True
        result["reason"] = explanation["reason"]
        result["category"] = "process_load_change"
        logger.info("Alert downgraded for %s: %s", motor_id, explanation["reason"])

    return result
