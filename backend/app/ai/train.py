"""Training script — trains all AI models and saves them.

Usage:
    python -m backend.app.ai.train
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.ai.anomaly import AnomalyEngine
from backend.app.ai.baseline import BaselineEngine
from backend.app.ai.fault_classifier import FaultClassifier
from backend.app.ai.features import engineer_features
from backend.app.core.config import load_config

logger = logging.getLogger(__name__)


def train_all(cfg: dict[str, Any]) -> dict[str, Any]:
    """Train all AI models and return metrics."""
    # Load training data
    csv_path = Path(cfg["paths"]["csv_path"])
    if not csv_path.exists():
        raise FileNotFoundError(f"Training data not found: {csv_path}. Run simulator first.")

    logger.info("Loading training data from %s", csv_path)
    df = pd.read_csv(csv_path, parse_dates=["Timestamp"])
    logger.info("Loaded %d rows", len(df))

    # Feature engineering
    windows = cfg["ai"]["rolling_windows"]
    df = engineer_features(df, windows)

    models_dir = Path(cfg["paths"]["models_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)

    metrics: dict[str, Any] = {}

    # 1. Train baselines
    logger.info("Training baseline models...")
    baseline_engine = BaselineEngine(models_dir)
    baseline_engine.train_all(df)
    baseline_engine.save_all()
    # Apply baseline so downstream models can use residual features
    df = baseline_engine.predict_all(df)
    metrics["baselines"] = {
        motor_id: {"trained": b.is_trained}
        for motor_id, b in baseline_engine.baselines.items()
    }

    # 2. Train anomaly detectors
    logger.info("Training anomaly detectors...")
    contamination = cfg["ai"]["contamination"]
    anomaly_engine = AnomalyEngine(models_dir, contamination)
    anomaly_engine.train_all(df)
    anomaly_engine.save_all()
    metrics["anomaly_detectors"] = {
        motor_id: {"trained": d.is_trained}
        for motor_id, d in anomaly_engine.detectors.items()
    }

    # 3. Train fault classifier
    logger.info("Training fault classifier...")
    classifier = FaultClassifier()
    clf_metrics = classifier.train(df)
    classifier.save(models_dir / "fault_classifier.joblib")
    metrics["fault_classifier"] = clf_metrics

    # 4. Save metrics
    metrics_path = Path(cfg["paths"]["metrics_path"])
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    logger.info("Metrics saved to %s", metrics_path)

    return metrics


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    metrics = train_all(cfg)
    print("Training complete!")
    print(f"Fault classifier F1: {metrics['fault_classifier'].get('f1', 0):.3f}")
    print(f"Models saved to: {cfg['paths']['models_dir']}")


if __name__ == "__main__":
    main()
