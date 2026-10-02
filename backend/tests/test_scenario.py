"""Test for report Section 15 scenario.

M2 vibration + temperature + current rising while M1/M3/M4 normal
→ M2-specific degradation warning.
"""
from __future__ import annotations

import pytest

from backend.app.ai.cross_asset import should_suppress_alert
from backend.app.ai.recommend import generate_recommendation


def test_m2_bearing_degradation_scenario():
    """Reproduce report Section 15 scenario.

    M2 shows bearing degradation (vibration + temp + current up)
    while M1/M3/M4 remain normal → should raise M2-specific alert.
    """
    # M2 readings with bearing degradation
    m2_reading = {
        "Current_A": 22.0,  # above nominal 18A
        "RPM": 2900.0,
        "Temperature_C": 65.0,  # above nominal 50°C
        "Vibration_g": 0.25,  # above nominal 0.10g
    }

    # Other motors normal
    all_readings = {
        "M2_Pump": m2_reading,
        "M1_Conveyor": {"Current_A": 12.0, "RPM": 1450.0},
        "M3_Compressor": {"Current_A": 25.0, "RPM": 1450.0},
        "M4_ProcessMachine": {"Current_A": 20.0, "RPM": 1750.0},
    }

    process_chain = [
        {"from": "M1_Conveyor", "to": "M2_Pump", "coupling": 0.6},
        {"from": "M2_Pump", "to": "M3_Compressor", "coupling": 0.5},
        {"from": "M3_Compressor", "to": "M4_ProcessMachine", "coupling": 0.4},
    ]

    # Cross-asset check: should NOT suppress (M1 is normal)
    result = should_suppress_alert(
        motor_id="M2_Pump",
        anomaly_score=0.85,
        all_readings=all_readings,
        process_chain=process_chain,
        cell_production=500.0,
        base_production=500.0,
    )

    assert result["suppress"] is False, "M2 fault should not be suppressed"

    # Recommendation should identify bearing degradation
    rec = generate_recommendation(
        motor_id="M2_Pump",
        motor_role="pump",
        predicted_fault="bearing_degradation",
        health_score=45.0,
        health_state="Critical",
        anomaly_score=0.85,
        temp_residual=15.0,
        vib_residual=0.15,
        current_residual=4.0,
        voltage_v=400.0,
        nominal_voltage=400.0,
        trend_info={"slope": -0.5},
        cross_asset_result=result,
    )

    assert "bearing" in rec["probable_cause"].lower()
    assert "inspect" in rec["recommended_action"].lower()
    assert rec["urgency"] == "high"


def test_process_load_change_not_flagged():
    """Cell-wide load increase should NOT be flagged as motor fault."""
    # All motors show increased load
    all_readings = {
        "M1_Conveyor": {"Current_A": 18.0, "RPM": 1500.0},
        "M2_Pump": {"Current_A": 25.0, "RPM": 2900.0},
        "M3_Compressor": {"Current_A": 32.0, "RPM": 1450.0},
        "M4_ProcessMachine": {"Current_A": 26.0, "RPM": 1750.0},
    }

    process_chain = [
        {"from": "M1_Conveyor", "to": "M2_Pump", "coupling": 0.6},
        {"from": "M2_Pump", "to": "M3_Compressor", "coupling": 0.5},
        {"from": "M3_Compressor", "to": "M4_ProcessMachine", "coupling": 0.4},
    ]

    result = should_suppress_alert(
        motor_id="M2_Pump",
        anomaly_score=0.7,
        all_readings=all_readings,
        process_chain=process_chain,
        cell_production=650.0,  # 30% above baseline
        base_production=500.0,
    )

    assert result["suppress"] is True, "Process load change should be suppressed"
    assert result["category"] == "process_load_change"
