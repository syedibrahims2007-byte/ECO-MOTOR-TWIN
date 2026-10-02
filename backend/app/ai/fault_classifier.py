"""Fault classification — RandomForest on labelled windows."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

FAULT_FEATURES = [
    "Current_A", "Power_kW", "Temperature_C", "Vibration_g",
    "RPM", "Power_Factor", "Voltage_V",
    "Current_A_roll_mean_5", "Temperature_C_roll_mean_5",
    "Vibration_g_roll_mean_5", "Vibration_g_roll_std_5",
    "Temperature_C_slope_5", "Current_A_slope_5",
    "Temp_Rise_Rate", "Vibration_g_rms",
]

FAULT_LABELS = ["normal", "overload", "overheating", "bearing_degradation", "imbalance", "voltage_sag"]


class FaultClassifier:
    """RandomForest classifier for fault types."""

    def __init__(self):
        self.model: RandomForestClassifier | None = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.classes: list[str] = []

    def train(self, df: pd.DataFrame) -> dict[str, Any]:
        """Train on labelled data with time-based split."""
        # Filter to labelled data
        labelled = df[df["Fault_Label"].isin(FAULT_LABELS)].copy()
        if len(labelled) < 50:
            logger.warning("Only %d labelled samples for fault classification", len(labelled))

        # Per-class time-block split: the first 75% of each fault class's
        # window trains, the last 25% tests. A global time-based split drops
        # late-window faults (overheating at frac 0.85-0.95) from training
        # entirely; a row-level stratified split leaks temporal neighbours
        # via rolling features. This keeps every class in both sets without
        # putting adjacent rows of the same window in train and test.
        labelled = labelled.sort_values("Timestamp")
        train_parts: list[pd.DataFrame] = []
        test_parts: list[pd.DataFrame] = []
        for _, group in labelled.groupby("Fault_Label"):
            group = group.sort_values("Timestamp")
            split_idx = max(1, int(len(group) * 0.75))
            train_parts.append(group.iloc[:split_idx])
            test_parts.append(group.iloc[split_idx:])
        train_df = pd.concat(train_parts, ignore_index=True)
        test_df = pd.concat(test_parts, ignore_index=True)

        feature_cols = [c for c in FAULT_FEATURES if c in train_df.columns]
        X_train = train_df[feature_cols].fillna(0).values
        y_train = train_df["Fault_Label"].values
        X_test = test_df[feature_cols].fillna(0).values
        y_test = test_df["Fault_Label"].values

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            random_state=42,
            class_weight="balanced",
        )
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True
        self.classes = list(self.model.classes_)

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        cm = confusion_matrix(y_test, y_pred, labels=self.classes)

        metrics = {
            "precision": report.get("weighted avg", {}).get("precision", 0),
            "recall": report.get("weighted avg", {}).get("recall", 0),
            "f1": report.get("weighted avg", {}).get("f1-score", 0),
            "confusion_matrix": cm.tolist(),
            "classes": self.classes,
            "train_samples": len(train_df),
            "test_samples": len(test_df),
        }
        logger.info(
            "Fault classifier trained: precision=%.3f recall=%.3f f1=%.3f",
            metrics["precision"], metrics["recall"], metrics["f1"],
        )
        return metrics

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict fault type for each row."""
        result = df.copy()
        if not self.is_trained or self.model is None:
            result["predicted_fault"] = "normal"
            result["fault_confidence"] = 0.0
            return result

        feature_cols = [c for c in FAULT_FEATURES if c in result.columns]
        X = result[feature_cols].fillna(0).values
        X_scaled = self.scaler.transform(X)

        predictions = self.model.predict(X_scaled)
        probabilities = self.model.predict_proba(X_scaled)
        confidence = probabilities.max(axis=1)

        result["predicted_fault"] = predictions
        result["fault_confidence"] = confidence
        return result

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str | Path) -> "FaultClassifier":
        return joblib.load(path)
