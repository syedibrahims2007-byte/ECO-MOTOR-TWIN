"""MQTT data source (stub for real hardware integration).

Requires paho-mqtt>=2.0 for actual use.

Configure mqtt section in config.yaml:
  mqtt:
    host: localhost
    port: 1883
    topic: ecomotortwin/sensors/+
"""
from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from backend.app.ingest.source_base import DataSource

logger = logging.getLogger(__name__)


class MqttSource(DataSource):
    """MQTT data source — stub implementation.

    To activate:
    1. pip install paho-mqtt>=2.0
    2. Configure mqtt section in config.yaml
    3. Replace SimulatedSource with MqttSource in main.py
    """

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg
        self._connected = False
        self._client = None
        self._buffer: list[dict[str, Any]] = []
        if cfg:
            self._mqtt_cfg = cfg.get("mqtt", {})
        else:
            self._mqtt_cfg = {}

    def connect(self) -> None:
        """Connect to MQTT broker."""
        try:
            import paho.mqtt.client as mqtt  # type: ignore

            host = self._mqtt_cfg.get("host", "localhost")
            port = self._mqtt_cfg.get("port", 1883)
            self._client = mqtt.Client()
            self._client.on_message = self._on_message
            self._client.connect(host, port)
            self._client.subscribe(self._mqtt_cfg.get("topic", "ecomotortwin/sensors/+"))
            self._client.loop_start()
            self._connected = True
            logger.info("MQTT connected to %s:%s", host, port)
        except ImportError:
            logger.error("paho-mqtt not installed — MqttSource is a stub")
            self._connected = False

    def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _on_message(self, client, userdata, msg) -> None:
        """Callback for incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode())
            self._buffer.append(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Failed to parse MQTT message: %s", e)

    def read(self) -> pd.DataFrame:
        """Return buffered messages as DataFrame."""
        if not self._connected:
            self.connect()
        if self._buffer:
            df = pd.DataFrame(self._buffer)
            self._buffer.clear()
            return df
        return pd.DataFrame()
