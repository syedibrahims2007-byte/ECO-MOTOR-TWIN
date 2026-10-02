"""Recommendation engine — rule + model based maintenance recommendations."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def generate_recommendation(
    motor_id: str,
    motor_role: str,
    predicted_fault: str,
    health_score: float,
    health_state: str,
    anomaly_score: float,
    temp_residual: float,
    vib_residual: float,
    current_residual: float,
    voltage_v: float,
    nominal_voltage: float,
    trend_info: dict[str, Any],
    cross_asset_result: dict[str, Any],
) -> dict[str, str]:
    """Generate maintenance recommendation with probable cause and action.

    Returns dict with:
    - probable_cause: str
    - evidence: str
    - recommended_action: str
    - urgency: str
    - confidence: str
    """
    # If cross-asset explains it, recommend monitoring not maintenance
    if cross_asset_result.get("suppress"):
        return {
            "probable_cause": "Process load change (not a motor fault)",
            "evidence": cross_asset_result.get("reason", ""),
            "recommended_action": "Continue monitoring; no maintenance action required",
            "urgency": "low",
            "confidence": "high",
        }

    # Fault-specific recommendations
    fault_rules = {
        "bearing_degradation": {
            "probable_cause": f"{motor_id}: bearing degradation",
            "evidence": (
                f"vibration +{vib_residual:.3f} g and temperature +{temp_residual:.1f} °C "
                f"above baseline with no change in upstream motors"
            ),
            "action": "Inspect/lubricate drive-end bearing within 48 h",
            "urgency": "high" if health_score < 60 else "medium",
        },
        "overheating": {
            "probable_cause": f"{motor_id}: overheating",
            "evidence": f"temperature +{temp_residual:.1f} °C above baseline",
            "action": "Check cooling system, ventilation, and load; inspect within 24 h",
            "urgency": "high" if health_score < 60 else "medium",
        },
        "overload": {
            "probable_cause": f"{motor_id}: overload condition",
            "evidence": f"current +{current_residual:.1f} A above expected for load",
            "action": "Check for mechanical binding, process overload, or misalignment",
            "urgency": "high" if health_score < 60 else "medium",
        },
        "imbalance": {
            "probable_cause": f"{motor_id}: rotor imbalance",
            "evidence": f"vibration +{vib_residual:.3f} g above baseline",
            "action": "Schedule balancing and alignment check within 1 week",
            "urgency": "medium",
        },
        "voltage_sag": {
            "probable_cause": f"{motor_id}: voltage sag",
            "evidence": f"voltage {voltage_v:.1f} V vs nominal {nominal_voltage:.1f} V",
            "action": "Check supply voltage, connections, and power quality",
            "urgency": "medium",
        },
    }

    if predicted_fault in fault_rules:
        rule = fault_rules[predicted_fault]
        confidence = "medium" if anomaly_score > 0.7 else "low"
        if cross_asset_result.get("downgrade"):
            confidence = "low (process-related)"

        return {
            "probable_cause": rule["probable_cause"],
            "evidence": rule["evidence"],
            "recommended_action": rule["action"],
            "urgency": rule["urgency"],
            "confidence": confidence,
        }

    # Default: no fault detected
    if health_state == "Healthy":
        return {
            "probable_cause": "Normal operation",
            "evidence": "All parameters within expected range",
            "recommended_action": "Continue normal operation",
            "urgency": "low",
            "confidence": "high",
        }

    return {
        "probable_cause": f"{motor_id}: minor deviation from baseline",
        "evidence": f"anomaly score {anomaly_score:.2f}, health {health_score:.0f}/100",
        "recommended_action": "Monitor closely; schedule inspection if trend continues",
        "urgency": "low",
        "confidence": "low",
    }
