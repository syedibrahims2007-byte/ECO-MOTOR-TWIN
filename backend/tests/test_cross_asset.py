"""Tests for cross-asset intelligence."""
from __future__ import annotations

import pytest

from backend.app.ai.cross_asset import (
    check_process_load_explanation,
    should_suppress_alert,
)


def test_process_load_explanation_no_upstream():
    """No upstream motors means no explanation."""
    result = check_process_load_explanation(
        motor_id="M1_Conveyor",
        motor_reading={"Current_A": 15.0, "RPM": 1450.0},
        all_readings={},
        process_chain=[],
    )
    assert result["is_explained"] is False


def test_process_load_explanation_with_upstream():
    """Upstream motor with increased load explains deviation."""
    result = check_process_load_explanation(
        motor_id="M2_Pump",
        motor_reading={"Current_A": 25.0, "RPM": 2900.0},
        all_readings={
            "M1_Conveyor": {"Current_A": 18.0, "RPM": 1500.0},
        },
        process_chain=[{"from": "M1_Conveyor", "to": "M2_Pump", "coupling": 0.6}],
    )
    assert result["is_explained"] is True
    assert "M1_Conveyor" in result["related_motors"]


def test_should_suppress_alert_process_load():
    """Alert suppressed when process load explains deviation."""
    result = should_suppress_alert(
        motor_id="M2_Pump",
        anomaly_score=0.8,
        all_readings={
            "M2_Pump": {"Current_A": 25.0, "RPM": 2900.0},
            "M1_Conveyor": {"Current_A": 18.0, "RPM": 1500.0},
        },
        process_chain=[{"from": "M1_Conveyor", "to": "M2_Pump", "coupling": 0.6}],
        cell_production=650.0,
        base_production=500.0,
    )
    assert result["suppress"] is True
    assert result["category"] == "process_load_change"


def test_should_not_suppress_motor_fault():
    """Alert not suppressed when no process explanation."""
    result = should_suppress_alert(
        motor_id="M2_Pump",
        anomaly_score=0.9,
        all_readings={
            "M2_Pump": {"Current_A": 30.0, "RPM": 2900.0},
            "M1_Conveyor": {"Current_A": 12.0, "RPM": 1450.0},
        },
        process_chain=[{"from": "M1_Conveyor", "to": "M2_Pump", "coupling": 0.6}],
        cell_production=500.0,
        base_production=500.0,
    )
    assert result["suppress"] is False
