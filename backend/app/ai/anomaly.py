"""Anomaly detection — IsolationForest + residual z-score + EWMA control chart."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

ANOMALY_FEATURES = [
    "Current_A", "Power_kW", "Temperature_C", "Vibration_g",
    "RPM", "Power_Factor",
]


class MotorAnomalyDetector:
    """Per-motor anomaly detector using IsolationForest + residual z-score."""

    def __init__(self, motor_id: str, contamination: float = 0.02):
        self.motor_id = motor_id
        self.contamination = contamination
        self.isolation_forest: IsolationForest | None = None
        self.scaler = StandardScaler()
        self.residual_mean: dict[str, float] = {}
        self.residual_std: dict[str, float] = {}
        self.ewma: dict[str, float] = {}
        self.is_trained = False

    def train(self, df: pd.DataFrame) -> None:
        """Train on normal data only."""
        normal = df[df.get("Fault_Label", "normal") == "normal"].copy()
        if len(normal) < 50:
            logger.warning("Motor %s: only %d normal samples", self.motor_id, len(normal))

        # IsolationForest on raw features
        X = normal[ANOMALY_FEATURES].fillna(0).values
        X_scaled = self.scaler.fit_transform(X)

        self.isolation_forest = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        self.isolation_forest.fit(X_scaled)

        # Residual statistics for z-score
        for target in ["Temperature_C", "Vibration_g", "Current_A"]:
            col = f"{target}_residual"
            if col in normal.columns:
                self.residual_mean[target] = normal[col].mean()
                self.residual_std[target] = normal[col].std() or 1.0

        self.is_trained = True
        logger.info("Motor %s: anomaly detector trained", self.motor_id)

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect anomalies, return DataFrame with anomaly_score column."""
        result = df.copy()
        if not self.is_trained or self.isolation_forest is None:
            result["anomaly_score"] = 0.0
            return result

        X = result[ANOMALY_FEATURES].fillna(0).values
        X_scaled = self.scaler.transform(X)

        # IsolationForest: -1 for anomaly, 1 for normal -> convert to 0-1 score
        raw_scores = self.isolation_forest.decision_function(X_scaled)
        # decision_function: negative = more anomalous, convert to 0-1
        if_scores = 1 - (raw_scores + 0.5)  # approximate normalization
        if_scores = np.clip(if_scores, 0, 1)

        # Residual z-score
        z_scores = np.zeros(len(result))
        for target in ["Temperature_C", "Vibration_g", "Current_A"]:
            col = f"{target}_residual"
            if col in result.columns and target in self.residual_std:
                z = (result[col] - self.residual_mean.get(target, 0)) / self.residual_std[target]
                z_scores = np.maximum(z_scores, np.abs(z))

        # EWMA on vibration
        if "Vibration_g" in result.columns:
            ewma = result["Vibration_g"].ewm(alpha=0.1).mean()
            ewma_z = np.abs(ewma - ewma.mean()) / (ewma.std() or 1.0)
            z_scores = np.maximum(z_scores, ewma_z.fillna(0).values)

        # Combine: max of IF score and normalized z-score
        result["anomaly_score"] = np.clip(np.maximum(if_scores, z_scores / 5), 0, 1)
        return result

    def save(self, path: str) -> None:
        import joblib
        joblib.dump(self, path)

    @staticmethod
    def load(path: str) -> "MotorAnomalyDetector":
        import joblib
        return joblib.load(path)


class AnomalyEngine:
    """Manages anomaly detectors for all motors."""

    def __init__(self, models_dir: str, contamination: float = 0.02):
        self.models_dir = models_dir
        self.contamination = contamination
        self.detectors: dict[str, MotorAnomalyDetector] = {}

    def train_all(self, df: pd.DataFrame) -> None:
        for motor_id in df["Motor"].unique():
            motor_df = df[df["Motor"] == motor_id]
            detector = MotorAnomalyDetector(motor_id, self.contamination)
            detector.train(motor_df)
            self.detectors[motor_id] = detector

    def detect_all(self, df: pd.DataFrame) -> pd.DataFrame:
        results = []
        for motor_id in df["Motor"].unique():
            motor_df = df[df["Motor"] == motor_id].copy()
            if motor_id in self.detectors:
                motor_df = self.detectors[motor_id].detect(motor_df)
            else:
                motor_df["anomaly_score"] = 0.0
            results.append(motor_df)
        return pd.concat(results, ignore_index=True) if results else df

    def save_all(self) -> None:
        import joblib
        for motor_id, detector in self.detectors.items():
            path = f"{self.models_dir}/anomaly_{motor_id}.joblib"
            detector.save(path)

    def load_all(self) -> None:
        import joblib
        from pathlib import Path
        for path in Path(self.models_dir).glob("anomaly_*.joblib"):
            detector = MotorAnomalyDetector.load(str(path))
            self.detectors[detector.motor_id] = detector
