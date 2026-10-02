"""Tests for the Digital Twin engine."""
from __future__ import annotations

import pytest

from backend.app.twin.motor_twin import MotorTwin
from backend.app.twin.cell_twin import CellTwin


def test_motor_twin_update():
    """Motor twin updates state from reading."""
    twin = MotorTwin(motor_id="M1_Conveyor", role="conveyor")
    reading = {
        "Voltage_V": 400.0,
        "Current_A": 12.0,
        "Power_kW": 6.5,
        "Temperature_C": 50.0,
        "RPM": 1450.0,
        "Vibration_g": 0.1,
        "Energy_kWh": 100.0,
        "Power_Factor": 0.85,
        "Operating_Hours": 50.0,
    }
    twin.update(reading, cell_production=500.0)
    assert twin.voltage_v == 400.0
    assert twin.current_a == 12.0
    assert twin.power_kw == 6.5
    assert twin.temperature_c == 50.0


def test_motor_twin_health_update():
    """Health score is clamped to 0-100."""
    twin = MotorTwin(motor_id="M1_Conveyor", role="conveyor")
    twin.update_health(85.0, "Healthy")
    assert twin.health_score == 85.0
    assert twin.health_state == "Healthy"

    twin.update_health(150.0, "Healthy")
    assert twin.health_score == 100.0

    twin.update_health(-10.0, "Critical")
    assert twin.health_score == 0.0


def test_motor_twin_to_dict():
    """to_dict returns all required fields."""
    twin = MotorTwin(motor_id="M1_Conveyor", role="conveyor")
    d = twin.to_dict()
    assert "motor_id" in d
    assert "health_score" in d
    assert "health_state" in d
    assert "voltage_v" in d
    assert "current_a" in d


def test_cell_twin_update():
    """Cell twin updates all motors."""
    motor_ids = ["M1_Conveyor", "M2_Pump", "M3_Compressor", "M4_ProcessMachine"]
    roles = {mid: "test" for mid in motor_ids}
    cell = CellTwin(motor_ids, roles)

    readings = {}
    for mid in motor_ids:
        readings[mid] = {
            "Voltage_V": 400.0,
            "Current_A": 10.0,
            "Power_kW": 5.0,
            "Temperature_C": 45.0,
            "RPM": 1450.0,
            "Vibration_g": 0.1,
            "Energy_kWh": 100.0,
            "Power_Factor": 0.85,
            "Operating_Hours": 10.0,
        }

    cell.update(readings, cell_production=500.0)
    assert len(cell.motors) == 4
    assert cell.cell_production_units_h == 500.0


def test_cell_twin_sec():
    """Cell SEC is computed correctly."""
    motor_ids = ["M1_Conveyor", "M2_Pump", "M3_Compressor", "M4_ProcessMachine"]
    roles = {mid: "test" for mid in motor_ids}
    cell = CellTwin(motor_ids, roles)

    readings = {}
    for mid in motor_ids:
        readings[mid] = {
            "Voltage_V": 400.0,
            "Current_A": 10.0,
            "Power_kW": 5.0,
            "Temperature_C": 45.0,
            "RPM": 1450.0,
            "Vibration_g": 0.1,
            "Energy_kwh": 100.0,
            "Power_Factor": 0.85,
            "Operating_Hours": 10.0,
        }

    cell.update(readings, cell_production=500.0)
    # Total power = 4 * 5 = 20 kW, production = 500
    # SEC = 20 / 500 = 0.04
    assert cell.cell_sec_kwh_per_unit == pytest.approx(0.04)
