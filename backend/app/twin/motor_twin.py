"""Motor Digital Twin — live computational representation of a single motor."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MotorTwin:
    """Digital twin for a single motor.

    Holds:
    - Current state (V, I, kW, kWh, PF, T, vibration, RPM)
    - Baseline (expected values for current load/speed)
    - Health state (Healthy / Warning / Critical)
    - Energy state (kW, kWh, SEC)
    - Maintenance state (operating hours, anomaly history, recommended action)
    """

    motor_id: str
    role: str
    # Current state
    voltage_v: float = 0.0
    current_a: float = 0.0
    power_kw: float = 0.0
    energy_kwh: float = 0.0
    power_factor: float = 0.85
    temperature_c: float = 25.0
    vibration_g: float = 0.0
    rpm: float = 0.0
    pressure_bar: float | None = None
    flow_lpm: float | None = None
    operating_hours: float = 0.0
    load: float = 0.0
    # Baseline (expected values)
    baseline_temp: float = 0.0
    baseline_vibration: float = 0.0
    baseline_current: float = 0.0
    # Health
    health_score: float = 100.0
    health_state: str = "Healthy"
    anomaly_score: float = 0.0
    predicted_fault: str = "normal"
    # Energy
    sec_kwh_per_unit: float | None = None
    # Maintenance
    anomaly_history: list[dict[str, Any]] = field(default_factory=list)
    recommended_action: str = ""
    # Metadata
    timestamp: datetime | None = None
    fault_label: str = "normal"

    def update(self, reading: dict[str, Any], cell_production: float = 0.0) -> None:
        """Update twin state from a new sensor reading."""
        self.timestamp = reading.get("Timestamp", datetime.now())
        self.voltage_v = reading.get("Voltage_V", self.voltage_v)
        self.current_a = reading.get("Current_A", self.current_a)
        self.power_kw = reading.get("Power_kW", self.power_kw)
        self.energy_kwh = reading.get("Energy_kWh", self.energy_kwh)
        self.power_factor = reading.get("Power_Factor", self.power_factor)
        self.temperature_c = reading.get("Temperature_C", self.temperature_c)
        self.vibration_g = reading.get("Vibration_g", self.vibration_g)
        self.rpm = reading.get("RPM", self.rpm)
        self.pressure_bar = reading.get("Pressure_bar", self.pressure_bar)
        self.flow_lpm = reading.get("Flow_lpm", self.flow_lpm)
        self.operating_hours = reading.get("Operating_Hours", self.operating_hours)
        self.fault_label = reading.get("Fault_Label", "normal")

        # Compute SEC if production data available
        if cell_production > 0 and self.power_kw > 0:
            # SEC for this motor's share of production
            self.sec_kwh_per_unit = self.power_kw / cell_production

    def update_baseline(self, expected_temp: float, expected_vibration: float, expected_current: float) -> None:
        """Update baseline expectations from AI model."""
        self.baseline_temp = expected_temp
        self.baseline_vibration = expected_vibration
        self.baseline_current = expected_current

    def update_health(self, score: float, state: str) -> None:
        """Update health score and state."""
        self.health_score = max(0.0, min(100.0, score))
        self.health_state = state

    def update_anomaly(self, score: float, predicted_fault: str = "normal") -> None:
        """Update anomaly detection results."""
        self.anomaly_score = score
        self.predicted_fault = predicted_fault
        if score > 0.7:
            self.anomaly_history.append({
                "timestamp": self.timestamp,
                "score": score,
                "fault": predicted_fault,
            })

    def to_dict(self) -> dict[str, Any]:
        """Serialize twin state to dict for API."""
        return {
            "motor_id": self.motor_id,
            "role": self.role,
            "voltage_v": round(self.voltage_v, 2),
            "current_a": round(self.current_a, 2),
            "power_kw": round(self.power_kw, 3),
            "energy_kwh": round(self.energy_kwh, 4),
            "power_factor": round(self.power_factor, 3),
            "temperature_c": round(self.temperature_c, 2),
            "vibration_g": round(self.vibration_g, 4),
            "rpm": round(self.rpm, 1),
            "pressure_bar": round(self.pressure_bar, 3) if self.pressure_bar else None,
            "flow_lpm": round(self.flow_lpm, 2) if self.flow_lpm else None,
            "operating_hours": round(self.operating_hours, 2),
            "load": round(self.load, 3),
            "baseline_temp": round(self.baseline_temp, 2),
            "baseline_vibration": round(self.baseline_vibration, 4),
            "baseline_current": round(self.baseline_current, 2),
            "health_score": round(self.health_score, 1),
            "health_state": self.health_state,
            "anomaly_score": round(self.anomaly_score, 3),
            "predicted_fault": self.predicted_fault,
            "sec_kwh_per_unit": round(self.sec_kwh_per_unit, 4) if self.sec_kwh_per_unit else None,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "fault_label": self.fault_label,
        }
