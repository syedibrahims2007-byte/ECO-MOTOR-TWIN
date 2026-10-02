"""Simulated data source — wraps the simulator for live ingestion."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from backend.app.core.config import load_config
from backend.app.ingest.source_base import DataSource
from backend.app.simulator.simulator import FourMotorSimulator

logger = logging.getLogger(__name__)


class SimulatedSource(DataSource):
    """Data source that generates simulated sensor readings."""

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or load_config()
        self.simulator = FourMotorSimulator(cfg=self.cfg)
        self._connected = False
        self._last_t_min = 0.0

    def connect(self) -> None:
        self._connected = True
        logger.info("SimulatedSource connected")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("SimulatedSource disconnected")

    def is_connected(self) -> bool:
        return self._connected

    def read(self) -> pd.DataFrame:
        """Generate one batch of live readings."""
        if not self._connected:
            self.connect()
        interval_min = self.cfg["simulator"]["live_sample_interval_sec"] / 60
        self._last_t_min += interval_min
        readings = self.simulator.step(self._last_t_min, interval_min)
        # Wall-clock timestamp for this live batch (unique per tick)
        ts = pd.Timestamp(datetime.now())
        rows = []
        for mid, vals in readings.items():
            row = dict(vals)
            row.setdefault("Timestamp", ts)
            rows.append(row)
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Demo controls (used by the REST API)
    # ------------------------------------------------------------------
    def inject_fault(
        self, motor: str, fault: str, duration_sec: int = 300, intensity: float = 1.0
    ) -> dict[str, Any]:
        """Inject an ad-hoc fault into the running simulation."""
        return self.simulator.inject_fault(
            motor, fault, duration_min=duration_sec / 60.0, intensity=intensity
        )

    def boost_process_load(self, duration_sec: int = 300, increase: float = 0.25) -> dict[str, Any]:
        """Raise load cell-wide (process change scenario)."""
        return self.simulator.boost_process_load(
            duration_min=duration_sec / 60.0, increase=increase
        )

    def reset(self) -> None:
        """Reset the simulator to a clean state."""
        self.simulator = FourMotorSimulator(cfg=self.cfg)
        self._last_t_min = 0.0
        logger.info("Simulator reset")
