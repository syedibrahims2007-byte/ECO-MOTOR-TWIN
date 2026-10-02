"""Tests for energy/SEC calculations."""
from __future__ import annotations

import pytest

from backend.app.energy.sec import compute_sec, flag_energy_waste


def test_compute_sec_basic():
    """SEC = kWh / unit."""
    assert compute_sec(10.0, 100.0) == 0.1


def test_compute_sec_zero_production():
    """SEC is None when production is zero."""
    assert compute_sec(10.0, 0.0) is None


def test_compute_sec_zero_energy():
    """SEC is zero when energy is zero."""
    assert compute_sec(0.0, 100.0) == 0.0


def test_flag_energy_waste_detected():
    """Energy waste flagged when SEC exceeds threshold."""
    result = flag_energy_waste(1.2, 1.0, threshold=1.15)
    assert result["is_waste"] is True
    assert result["ratio"] == 1.2


def test_flag_energy_waste_not_detected():
    """No waste when SEC is below threshold."""
    result = flag_energy_waste(1.1, 1.0, threshold=1.15)
    assert result["is_waste"] is False


def test_flag_energy_waste_no_baseline():
    """No waste when baseline is zero."""
    result = flag_energy_waste(1.2, 0.0)
    assert result["is_waste"] is False
