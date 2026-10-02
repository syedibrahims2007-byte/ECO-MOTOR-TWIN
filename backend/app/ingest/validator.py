"""Data validation for incoming sensor readings."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Valid ranges for sensor values
VALID_RANGES = {
    "Voltage_V": (0, 500),
    "Current_A": (0, 100),
    "Power_kW": (0, 50),
    "Temperature_C": (-20, 150),
    "RPM": (0, 5000),
    "Vibration_g": (0, 2),
    "Power_Factor": (0, 1),
    "Pressure_bar": (0, 20),
    "Flow_lpm": (0, 1000),
    "Operating_Hours": (0, 100000),
    "Cell_Production_units_h": (0, 10000),
}


def validate_readings(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean a readings DataFrame.

    - Checks required columns exist
    - Clips values to valid ranges
    - Removes duplicate timestamps per motor
    - Sorts by timestamp
    - Logs warnings for out-of-range values
    """
    if df.empty:
        return df

    required = ["Timestamp", "Motor"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Ensure Timestamp is datetime
    df = df.copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])

    # Remove duplicates
    before = len(df)
    df = df.drop_duplicates(subset=["Timestamp", "Motor"], keep="last")
    if len(df) < before:
        logger.warning("Removed %d duplicate readings", before - len(df))

    # Sort by timestamp
    df = df.sort_values("Timestamp").reset_index(drop=True)

    # Clip to valid ranges
    for col, (lo, hi) in VALID_RANGES.items():
        if col in df.columns:
            out_of_range = ((df[col] < lo) | (df[col] > hi)).sum()
            if out_of_range > 0:
                logger.warning(
                    "%s: %d values out of range [%s, %s], clipping",
                    col, out_of_range, lo, hi,
                )
                df[col] = df[col].clip(lo, hi)

    # Check for missing values
    missing = df.isnull().sum()
    for col, count in missing.items():
        if count > 0 and col not in ("Pressure_bar", "Flow_lpm"):
            logger.warning("%s: %d missing values", col, count)

    return df
