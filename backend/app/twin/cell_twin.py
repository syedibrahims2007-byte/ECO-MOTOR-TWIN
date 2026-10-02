"""Cell Digital Twin — aggregate of four motors with process relationships."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from backend.app.twin.motor_twin import MotorTwin

logger = logging.getLogger(__name__)


class CellTwin:
    """Digital twin for the four-motor production cell.

    Holds all four MotorTwins, their process relationships,
    cell energy, production and SEC.
    """

    def __init__(self, motor_ids: list[str], motor_roles: dict[str, str]):
        self.motors: dict[str, MotorTwin] = {
            mid: MotorTwin(motor_id=mid, role=motor_roles.get(mid, "unknown"))
            for mid in motor_ids
        }
        self.total_energy_kwh = 0.0
        self.cell_production_units_h = 0.0
        self.cell_sec_kwh_per_unit: float | None = None
        self.sec_baseline: float | None = None
        self.timestamp: datetime | None = None

    def update(self, readings: dict[str, dict[str, Any]], cell_production: float = 0.0) -> None:
        """Update all motor twins from readings."""
        self.cell_production_units_h = cell_production
        total_power = 0.0
        total_energy = 0.0

        for mid, reading in readings.items():
            if mid in self.motors:
                self.motors[mid].update(reading, cell_production)
                total_power += self.motors[mid].power_kw
                total_energy += self.motors[mid].energy_kwh
                self.timestamp = self.motors[mid].timestamp

        self.total_energy_kwh = total_energy

        # Cell SEC
        if cell_production > 0 and total_power > 0:
            self.cell_sec_kwh_per_unit = total_power / cell_production

    def set_sec_baseline(self, baseline: float) -> None:
        """Set the learned SEC baseline for similar production levels."""
        self.sec_baseline = baseline

    def get_motor(self, motor_id: str) -> MotorTwin | None:
        """Get a specific motor twin."""
        return self.motors.get(motor_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize cell state to dict for API."""
        motor_dicts = [m.to_dict() for m in self.motors.values()]
        return {
            "motors": motor_dicts,
            "total_power_kw": round(sum(m.power_kw for m in self.motors.values()), 3),
            "total_energy_kwh": round(self.total_energy_kwh, 4),
            "cell_production_units_h": round(self.cell_production_units_h, 1),
            "cell_sec_kwh_per_unit": round(self.cell_sec_kwh_per_unit, 4) if self.cell_sec_kwh_per_unit else None,
            "sec_baseline": round(self.sec_baseline, 4) if self.sec_baseline else None,
            "sec_ratio": round(self.cell_sec_kwh_per_unit / self.sec_baseline, 3) if self.sec_baseline and self.cell_sec_kwh_per_unit else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
