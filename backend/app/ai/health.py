"""Health index computation — weighted combination of indicators."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_health_score(
    anomaly_score: float,
    temp_residual: float,
    vib_residual: float,
    current_residual: float,
    trend_slope: float,
    healthy_threshold: float = 80.0,
    warning_threshold: float = 60.0,
) -> tuple[float, str]:
    """Compute health index (0-100) and state.

    Weighted combination:
    - Anomaly score: 40%
    - Temperature residual: 20%
    - Vibration residual: 20%
    - Current residual: 10%
    - Trend slope: 10%

    Returns:
        (health_score, health_state)
    """
    # Normalize residuals to 0-1 scale (assuming residuals are in physical units)
    temp_penalty = min(abs(temp_residual) / 20.0, 1.0)  # 20°C residual = max penalty
    vib_penalty = min(abs(vib_residual) / 0.3, 1.0)  # 0.3g residual = max penalty
    curr_penalty = min(abs(current_residual) / 10.0, 1.0)  # 10A residual = max penalty
    trend_penalty = min(abs(trend_slope) * 10, 1.0)  # slope penalty

    # Weighted penalty (0 = no penalty, 1 = max penalty)
    penalty = (
        0.40 * anomaly_score
        + 0.20 * temp_penalty
        + 0.20 * vib_penalty
        + 0.10 * curr_penalty
        + 0.10 * trend_penalty
    )

    health_score = max(0.0, 100.0 * (1 - penalty))

    if health_score >= healthy_threshold:
        state = "Healthy"
    elif health_score >= warning_threshold:
        state = "Warning"
    else:
        state = "Critical"

    return round(health_score, 1), state


def compute_health_for_motor(
    df: pd.DataFrame,
    motor_id: str,
    healthy_threshold: float = 80.0,
    warning_threshold: float = 60.0,
) -> pd.DataFrame:
    """Compute health index for a single motor's data."""
    motor_df = df[df["Motor"] == motor_id].copy()

    scores = []
    states = []
    for _, row in motor_df.iterrows():
        score, state = compute_health_score(
            anomaly_score=row.get("anomaly_score", 0.0),
            temp_residual=row.get("Temperature_C_residual", 0.0),
            vib_residual=row.get("Vibration_g_residual", 0.0),
            current_residual=row.get("Current_A_residual", 0.0),
            trend_slope=row.get("health_trend_slope", 0.0),
            healthy_threshold=healthy_threshold,
            warning_threshold=warning_threshold,
        )
        scores.append(score)
        states.append(state)

    motor_df["health_score"] = scores
    motor_df["health_state"] = states
    return motor_df
