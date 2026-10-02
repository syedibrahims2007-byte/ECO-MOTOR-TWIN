"""Feature engineering for time-series sensor data."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "Voltage_V", "Current_A", "Power_kW", "Temperature_C",
    "RPM", "Vibration_g", "Power_Factor",
]


def compute_rolling_features(
    df: pd.DataFrame,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Compute rolling mean/std/slope for each motor.

    Args:
        df: Input DataFrame with Timestamp, Motor, and sensor columns
        windows: List of window sizes in samples (default from config)

    Returns:
        DataFrame with added rolling feature columns
    """
    if windows is None:
        windows = [1, 5, 15]

    df = df.copy()
    df = df.sort_values(["Motor", "Timestamp"]).reset_index(drop=True)

    for motor in df["Motor"].unique():
        mask = df["Motor"] == motor
        motor_df = df.loc[mask]

        for col in FEATURE_COLUMNS:
            if col not in motor_df.columns:
                continue
            for w in windows:
                df.loc[mask, f"{col}_roll_mean_{w}"] = (
                    motor_df[col].rolling(w, min_periods=1).mean()
                )
                df.loc[mask, f"{col}_roll_std_{w}"] = (
                    motor_df[col].rolling(w, min_periods=1).std().fillna(0)
                )
                # Slope (difference over window)
                df.loc[mask, f"{col}_slope_{w}"] = (
                    motor_df[col].diff(w).fillna(0) / w
                )

    return df


def compute_rms_vibration(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Compute RMS vibration over rolling window."""
    df = df.copy()
    for motor in df["Motor"].unique():
        mask = df["Motor"] == motor
        motor_df = df.loc[mask]
        df.loc[mask, "Vibration_g_rms"] = np.sqrt(
            motor_df["Vibration_g"].rolling(window, min_periods=1).apply(
                lambda x: np.mean(x**2), raw=True
            )
        )
    return df


def compute_temperature_rise_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Compute temperature rise rate (°C per minute)."""
    df = df.copy()
    df = df.sort_values(["Motor", "Timestamp"])
    for motor in df["Motor"].unique():
        mask = df["Motor"] == motor
        motor_df = df.loc[mask]
        dt_min = motor_df["Timestamp"].diff().dt.total_seconds() / 60
        dt_min = dt_min.fillna(1).replace(0, 1)
        df.loc[mask, "Temp_Rise_Rate"] = motor_df["Temperature_C"].diff().fillna(0) / dt_min
    return df


def compute_load_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute load-normalized features (per-unit-load values)."""
    df = df.copy()
    # Avoid division by zero
    load = df.get("Load", pd.Series(1.0, index=df.index))
    load = load.replace(0, 0.01)

    df["Current_per_Load"] = df["Current_A"] / load
    df["Power_per_Load"] = df["Power_kW"] / load
    df["Vibration_per_Load"] = df["Vibration_g"] / load
    df["Temp_per_Load"] = df["Temperature_C"] / load
    return df


def engineer_features(df: pd.DataFrame, windows: list[int] | None = None) -> pd.DataFrame:
    """Full feature engineering pipeline."""
    logger.info("Engineering features for %d rows", len(df))
    df = compute_rolling_features(df, windows)
    df = compute_rms_vibration(df)
    df = compute_temperature_rise_rate(df)
    df = compute_load_normalized_features(df)
    logger.info("Feature engineering complete: %d columns", len(df.columns))
    return df
