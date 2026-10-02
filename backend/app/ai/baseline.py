"""Baseline model — learns normal behaviour per motor.

Trains a regression model to predict expected temperature, vibration,
and current from load/speed/ambient. Residual = actual - expected.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

TARGETS = ["Temperature_C", "Vibration_g", "Current_A"]
FEATURES_FOR_BASELINE = ["RPM", "Power_Factor", "Load"]


class MotorBaseline:
    """Per-motor baseline model."""

    def __init__(self, motor_id: str):
        self.motor_id = motor_id
        self.models: dict[str, Any] = {}
        self.scalers: dict[str, StandardScaler] = {}
        self.is_trained = False

    def train(self, df: pd.DataFrame) -> None:
        """Train baseline models on normal data only."""
        normal = df[df.get("Fault_Label", "normal") == "normal"].copy()
        if len(normal) < 100:
            logger.warning(
                "Motor %s: only %d normal samples for baseline", self.motor_id, len(normal)
            )

        for target in TARGETS:
            if target not in normal.columns:
                continue
            X = normal[FEATURES_FOR_BASELINE].fillna(0).values
            y = normal[target].values

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42,
            )
            model.fit(X_scaled, y)

            self.models[target] = model
            self.scalers[target] = scaler

        self.is_trained = True
        logger.info("Motor %s: baseline trained on %d samples", self.motor_id, len(normal))

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict expected values and compute residuals."""
        result = df.copy()
        for target in TARGETS:
            if target not in self.models or target not in result.columns:
                continue
            X = result[FEATURES_FOR_BASELINE].fillna(0).values
            X_scaled = self.scalers[target].transform(X)
            predicted = self.models[target].predict(X_scaled)
            result[f"{target}_expected"] = predicted
            result[f"{target}_residual"] = result[target] - predicted
        return result

    def save(self, path: str | Path) -> None:
        """Save baseline model to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("Motor %s: baseline saved to %s", self.motor_id, path)

    @staticmethod
    def load(path: str | Path) -> "MotorBaseline":
        """Load baseline model from disk."""
        return joblib.load(path)


class BaselineEngine:
    """Manages baseline models for all motors."""

    def __init__(self, models_dir: str | Path):
        self.models_dir = Path(models_dir)
        self.baselines: dict[str, MotorBaseline] = {}

    def train_all(self, df: pd.DataFrame) -> None:
        """Train baselines for all motors."""
        for motor_id in df["Motor"].unique():
            motor_df = df[df["Motor"] == motor_id]
            baseline = MotorBaseline(motor_id)
            baseline.train(motor_df)
            self.baselines[motor_id] = baseline

    def predict_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict for all motors."""
        results = []
        for motor_id in df["Motor"].unique():
            motor_df = df[df["Motor"] == motor_id].copy()
            if motor_id in self.baselines:
                motor_df = self.baselines[motor_id].predict(motor_df)
            results.append(motor_df)
        return pd.concat(results, ignore_index=True) if results else df

    def save_all(self) -> None:
        """Save all baseline models."""
        for motor_id, baseline in self.baselines.items():
            path = self.models_dir / f"baseline_{motor_id}.joblib"
            baseline.save(path)

    def load_all(self) -> None:
        """Load all baseline models."""
        for path in self.models_dir.glob("baseline_*.joblib"):
            baseline = MotorBaseline.load(path)
            self.baselines[baseline.motor_id] = baseline
