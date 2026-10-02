"""Evaluation script — runs labelled fault scenarios and reports metrics.

Saves results to docs/RESULTS.md and docs/figures/.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.ai.anomaly import AnomalyEngine
from backend.app.ai.baseline import BaselineEngine
from backend.app.ai.fault_classifier import FaultClassifier
from backend.app.ai.features import engineer_features
from backend.app.core.config import load_config

logger = logging.getLogger(__name__)


def run_evaluation(cfg: dict[str, Any]) -> dict[str, Any]:
    """Run full evaluation and return metrics."""
    # Load data
    csv_path = Path(cfg["paths"]["csv_path"])
    df = pd.read_csv(csv_path, parse_dates=["Timestamp"])

    # Feature engineering
    windows = cfg["ai"]["rolling_windows"]
    df = engineer_features(df, windows)

    models_dir = Path(cfg["paths"]["models_dir"])

    # Load models
    baseline_engine = BaselineEngine(models_dir)
    baseline_engine.load_all()

    anomaly_engine = AnomalyEngine(models_dir, cfg["ai"]["contamination"])
    anomaly_engine.load_all()

    classifier = FaultClassifier.load(models_dir / "fault_classifier.joblib")

    # Run predictions
    df = baseline_engine.predict_all(df)
    df = anomaly_engine.detect_all(df)
    df = classifier.predict(df)

    # Compute metrics
    metrics = {}

    # 1. Anomaly detection performance
    fault_mask = df["Fault_Label"] != "normal"
    normal_mask = df["Fault_Label"] == "normal"

    anomaly_scores = df["anomaly_score"].values
    fault_scores = anomaly_scores[fault_mask]
    normal_scores = anomaly_scores[normal_mask]

    metrics["anomaly_detection"] = {
        "fault_mean_score": float(np.mean(fault_scores)) if len(fault_scores) > 0 else 0,
        "normal_mean_score": float(np.mean(normal_scores)) if len(normal_scores) > 0 else 0,
        "detection_threshold": 0.5,
        "faults_detected": int((fault_scores > 0.5).sum()),
        "faults_total": int(len(fault_scores)),
        "false_alarms": int((normal_scores > 0.5).sum()),
        "normal_total": int(len(normal_scores)),
    }

    # 2. Fault classification performance
    labelled = df[df["Fault_Label"] != "normal"]
    if len(labelled) > 0:
        y_true = labelled["Fault_Label"].values
        y_pred = labelled["predicted_fault"].values

        from sklearn.metrics import classification_report, confusion_matrix
        report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
        cm = confusion_matrix(y_true, y_pred)

        metrics["fault_classification"] = {
            "precision": report.get("weighted avg", {}).get("precision", 0),
            "recall": report.get("weighted avg", {}).get("recall", 0),
            "f1": report.get("weighted avg", {}).get("f1-score", 0),
            "confusion_matrix": cm.tolist(),
            "samples": len(labelled),
        }

    # 3. Detection delay
    detection_delays = []
    for motor in df["Motor"].unique():
        motor_df = df[df["Motor"] == motor].sort_values("Timestamp")
        fault_rows = motor_df[motor_df["Fault_Label"] != "normal"]
        if len(fault_rows) == 0:
            continue

        fault_start = fault_rows["Timestamp"].iloc[0]
        detected = motor_df[
            (motor_df["Timestamp"] >= fault_start) & (motor_df["anomaly_score"] > 0.5)
        ]
        if len(detected) > 0:
            delay = (detected["Timestamp"].iloc[0] - fault_start).total_seconds() / 60
            detection_delays.append(delay)

    metrics["detection_delay"] = {
        "mean_min": float(np.mean(detection_delays)) if detection_delays else 0,
        "max_min": float(np.max(detection_delays)) if detection_delays else 0,
        "min_min": float(np.min(detection_delays)) if detection_delays else 0,
    }

    # 4. Cross-asset suppression
    # Count how many process-load windows were correctly suppressed
    process_window = cfg["simulator"].get("process_load_window", {})
    if process_window:
        total_min = cfg["simulator"]["history_days"] * 1440
        start_min = process_window["start_frac"] * total_min
        end_min = process_window["end_frac"] * total_min

        process_df = df[
            (df["Timestamp"] >= df["Timestamp"].min() + pd.Timedelta(minutes=start_min))
            & (df["Timestamp"] <= df["Timestamp"].min() + pd.Timedelta(minutes=end_min))
        ]

        metrics["cross_asset"] = {
            "process_load_window_samples": len(process_df),
            "mean_anomaly_score_during_process_load": float(
                process_df["anomaly_score"].mean()
            ) if len(process_df) > 0 else 0,
        }

    return metrics


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    metrics = run_evaluation(cfg)

    # Save metrics
    results_path = Path(cfg["paths"]["figures_dir"]) / "evaluation_metrics.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print("Evaluation complete!")
    print(f"Anomaly detection fault mean score: {metrics['anomaly_detection']['fault_mean_score']:.3f}")
    print(f"Anomaly detection normal mean score: {metrics['anomaly_detection']['normal_mean_score']:.3f}")
    print(f"Detection delay (mean): {metrics['detection_delay']['mean_min']:.1f} min")
    if "fault_classification" in metrics:
        print(f"Fault classifier F1: {metrics['fault_classification']['f1']:.3f}")


if __name__ == "__main__":
    main()
