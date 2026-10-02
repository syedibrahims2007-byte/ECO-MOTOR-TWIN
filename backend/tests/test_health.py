"""Tests for health index computation."""
from __future__ import annotations

import pytest

from backend.app.ai.health import compute_health_score


def test_healthy_score():
    """Perfect conditions give score >= 80."""
    score, state = compute_health_score(
        anomaly_score=0.0,
        temp_residual=0.0,
        vib_residual=0.0,
        current_residual=0.0,
        trend_slope=0.0,
    )
    assert score >= 80
    assert state == "Healthy"


def test_critical_score():
    """Severe conditions give score < 60."""
    score, state = compute_health_score(
        anomaly_score=1.0,
        temp_residual=20.0,
        vib_residual=0.3,
        current_residual=10.0,
        trend_slope=0.1,
    )
    assert score < 60
    assert state == "Critical"


def test_warning_score():
    """Moderate conditions give score 60-79."""
    score, state = compute_health_score(
        anomaly_score=0.3,
        temp_residual=5.0,
        vib_residual=0.08,
        current_residual=2.0,
        trend_slope=0.02,
    )
    assert 60 <= score < 80
    assert state == "Warning"


def test_score_bounds():
    """Score is always 0-100."""
    for anomaly in [0.0, 0.5, 1.0]:
        for temp in [0.0, 10.0, 30.0]:
            score, _ = compute_health_score(
                anomaly_score=anomaly,
                temp_residual=temp,
                vib_residual=0.1,
                current_residual=5.0,
                trend_slope=0.05,
            )
            assert 0 <= score <= 100
