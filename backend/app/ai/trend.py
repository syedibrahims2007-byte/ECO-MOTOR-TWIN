"""Trend / degradation analysis — Theil-Sen slope of health index and residuals."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

logger = logging.getLogger(__name__)


def compute_trend_slope(values: np.ndarray, window: int = 60) -> float:
    """Compute Theil-Sen slope over a rolling window.

    Returns slope in units of value per sample.
    """
    if len(values) < 2:
        return 0.0
    w = min(window, len(values))
    recent = values[-w:]
    x = np.arange(len(recent))
    try:
        slope, _, _, _ = theilslopes(recent, x)
        return float(slope)
    except Exception:
        return 0.0


def compute_degradation_trend(
    health_scores: np.ndarray,
    warning_threshold: float = 60.0,
    critical_threshold: float = 40.0,
    window: int = 60,
) -> dict[str, Any]:
    """Compute degradation trend and time-to-threshold estimates.

    Returns dict with:
    - slope: health score change per sample
    - hours_until_warning: estimated hours until warning threshold (if trend continues)
    - hours_until_critical: estimated hours until critical threshold
    - confidence: note about confidence (never claims exact failure date)
    """
    if len(health_scores) < 2:
        return {
            "slope": 0.0,
            "hours_until_warning": None,
            "hours_until_critical": None,
            "confidence": "insufficient data",
        }

    slope = compute_trend_slope(health_scores, window)
    current = health_scores[-1]

    result = {
        "slope": round(slope, 4),
        "hours_until_warning": None,
        "hours_until_critical": None,
        "confidence": "",
    }

    if slope >= 0:
        result["confidence"] = "no degradation trend detected"
        return result

    # Estimate time to thresholds (slope is per sample, assume 1 sample/min)
    if current > warning_threshold:
        samples_to_warning = (current - warning_threshold) / abs(slope)
        result["hours_until_warning"] = round(samples_to_warning / 60, 1)

    if current > critical_threshold:
        samples_to_critical = (current - critical_threshold) / abs(slope)
        result["hours_until_critical"] = round(samples_to_critical / 60, 1)

    result["confidence"] = (
        "trend-based estimate, not a prediction; "
        "actual time depends on operating conditions and fault progression"
    )

    return result


def add_trend_features(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Add trend slope features to DataFrame."""
    df = df.copy()
    df = df.sort_values(["Motor", "Timestamp"])

    for motor in df["Motor"].unique():
        mask = df["Motor"] == motor
        motor_df = df.loc[mask]

        for col in ["Temperature_C", "Vibration_g", "Current_A", "health_score"]:
            if col in motor_df.columns:
                slopes = []
                values = motor_df[col].values
                for i in range(len(values)):
                    start = max(0, i - window + 1)
                    slope = compute_trend_slope(values[start:i + 1], window)
                    slopes.append(slope)
                df.loc[mask, f"{col}_trend_slope"] = slopes

    return df
