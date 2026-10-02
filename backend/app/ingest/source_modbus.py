"""Modbus RTU/TCP data source (stub for real hardware integration).

Register map is defined in config.yaml under modbus.register_map.
Requires pymodbus>=3.0 for actual use.

Example register map:
  M1_Conveyor:
    voltage_v: {address: 0, type: input_register, scale: 0.1}
    current_a: {address: 1, type: input_register, scale: 0.01}
    ...
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from backend.app.ingest.source_base import DataSource

logger = logging.getLogger(__name__)


class ModbusSource(DataSource):
    """Modbus data source — stub implementation.

    To activate:
    1. pip install pymodbus>=3.0
    2. Configure modbus section in config.yaml
    3. Replace SimulatedSource with ModbusSource in main.py
    """

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg
        self._connected = False
        self._client = None
        self._register_map = {}
        if cfg:
            self._register_map = cfg.get("modbus", {}).get("register_map", {})

    def connect(self) -> None:
        """Connect to Modbus device."""
        try:
            from pymodbus.client import ModbusTcpClient  # type: ignore

            host = self.cfg.get("modbus", {}).get("host", "localhost")
            port = self.cfg.get("modbus", {}).get("port", 502)
            self._client = ModbusTcpClient(host, port=port)
            self._connected = self._client.connect()
            logger.info("Modbus connected to %s:%s", host, port)
        except ImportError:
            logger.error("pymodbus not installed — ModbusSource is a stub")
            self._connected = False

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def read(self) -> pd.DataFrame:
        """Read registers and return DataFrame."""
        if not self._connected:
            self.connect()
        # Stub: return empty DataFrame with correct columns
        # Real implementation would read registers per motor
        logger.warning("ModbusSource.read() not fully implemented — stub")
        return pd.DataFrame()
