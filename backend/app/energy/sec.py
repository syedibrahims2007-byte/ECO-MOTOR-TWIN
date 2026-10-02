"""Specific Energy Consumption (SEC) analysis.

SEC = Energy (kWh) / Production (units)
Compares current SEC with learned baseline for similar production levels.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_sec(energy_kwh: float, production_units: float) -> float | None:
    """Compute SEC = kWh / unit."""
    if production_units <= 0:
        return None
    return energy_kwh / production_units


def compute_motor_sec(
    motor_energy_kwh: float,
    cell_production: float,
    production_share: float,
) -> float | None:
    """Compute SEC for a motor's share of production."""
    if cell_production <= 0:
        return None
    # Motor's share of production
    motor_production = cell_production * production_share
    return motor_energy_kwh / motor_production


def compute_cell_sec(df: pd.DataFrame) -> pd.DataFrame:
    """Compute cell-level SEC from readings."""
    df = df.copy()
    # Group by timestamp to get cell totals
    cell = df.groupby("Timestamp").agg({
        "Energy_kWh": "sum",
        "Cell_Production_units_h": "first",
    }).reset_index()
    cell["cell_sec_kwh_per_unit"] = cell["Energy_kWh"] / cell["Cell_Production_units_h"]
    return cell


def learn_sec_baseline(
    df: pd.DataFrame,
    window: int = 1440,
) -> float:
    """Learn SEC baseline from normal-operation data.

    Uses rolling median of SEC during normal operation.
    """
    normal = df[df.get("Fault_Label", "normal") == "normal"].copy()
    if len(normal) < 100:
        logger.warning("Insufficient normal data for SEC baseline")
        return 0.0

    # Compute SEC per timestamp
    cell = compute_cell_sec(normal)
    sec_values = cell["cell_sec_kwh_per_unit"].dropna()

    if len(sec_values) == 0:
        return 0.0

    # Use median as baseline (robust to outliers)
    baseline = float(sec_values.median())
    logger.info("SEC baseline learned: %.4f kWh/unit (from %d samples)", baseline, len(sec_values))
    return baseline


def flag_energy_waste(
    current_sec: float,
    baseline_sec: float,
    threshold: float = 1.15,
) -> dict[str, Any]:
    """Flag energy waste vs higher production.

    Returns dict with:
    - is_waste: bool — True if SEC exceeds baseline by threshold
    - ratio: float — current SEC / baseline SEC
    - reason: str
    """
    if baseline_sec <= 0:
        return {"is_waste": False, "ratio": 0.0, "reason": "no baseline available"}

    ratio = current_sec / baseline_sec
    is_waste = ratio > threshold

    if is_waste:
        reason = f"SEC {ratio:.2f}x baseline — energy waste detected (inefficient operation)"
    elif ratio > 1.0:
        reason = f"SEC {ratio:.2f}x baseline — slightly elevated, monitor"
    else:
        reason = f"SEC {ratio:.2f}x baseline — efficient operation"

    return {"is_waste": is_waste, "ratio": round(ratio, 3), "reason": reason}
