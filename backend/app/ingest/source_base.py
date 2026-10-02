"""Abstract base class for data sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class DataSource(ABC):
    """Abstract interface for all data sources (simulator, Modbus, MQTT)."""

    @abstractmethod
    def read(self) -> pd.DataFrame:
        """Read new data and return as DataFrame."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the data source."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if source is connected and ready."""
        ...
