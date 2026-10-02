"""Tests for the simulator."""
from __future__ import annotations

import pytest

from backend.app.core.config import load_config
from backend.app.simulator.simulator import FourMotorSimulator


@pytest.fixture
def sim():
    cfg = load_config()
    return FourMotorSimulator(cfg=cfg)


def test_simulator_generates_monotonic_timestamps(sim):
    """Timestamps must be strictly increasing."""
    df = sim.generate_history()
    ts = df["Timestamp"].unique()
    assert len(ts) > 1
    for i in range(1, len(ts)):
        assert ts[i] > ts[i - 1]


def test_simulator_generates_all_motors(sim):
    """All four motors must be present."""
    df = sim.generate_history()
    motors = df["Motor"].unique()
    assert len(motors) == 4
    assert "M1_Conveyor" in motors
    assert "M2_Pump" in motors
    assert "M3_Compressor" in motors
    assert "M4_ProcessMachine" in motors


def test_energy_is_cumulative(sim):
    """Energy must be non-decreasing."""
    df = sim.generate_history()
    for motor in df["Motor"].unique():
        motor_df = df[df["Motor"] == motor].sort_values("Timestamp")
        energy = motor_df["Energy_kWh"].values
        for i in range(1, len(energy)):
            assert energy[i] >= energy[i - 1]


def test_fault_labels_present(sim):
    """Fault labels must be present in the data."""
    df = sim.generate_history()
    labels = df["Fault_Label"].unique()
    assert "normal" in labels
    # At least one fault type should be present
    non_normal = [l for l in labels if l != "normal"]
    assert len(non_normal) > 0


def test_m2_has_normal_baseline(sim):
    """M2 must have normal (non-fault) data for baseline training."""
    df = sim.generate_history()
    m2_df = df[df["Motor"] == "M2_Pump"]
    normal_count = (m2_df["Fault_Label"] == "normal").sum()
    assert normal_count > 100, f"M2 only has {normal_count} normal samples"


def test_power_factor_in_valid_range(sim):
    """Power factor must be between 0 and 1."""
    df = sim.generate_history()
    pf = df["Power_Factor"].dropna()
    assert (pf >= 0).all() and (pf <= 1).all()


def test_cell_production_positive(sim):
    """Cell production must be positive."""
    df = sim.generate_history()
    prod = df["Cell_Production_units_h"].dropna()
    assert (prod > 0).all()
