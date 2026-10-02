"""Pydantic schemas for API request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MotorState(BaseModel):
    """Current state of a single motor."""

    motor_id: str
    role: str
    voltage_v: float
    current_a: float
    power_kw: float
    temperature_c: float
    rpm: float
    vibration_g: float
    energy_kwh: float
    power_factor: float
    pressure_bar: Optional[float] = None
    flow_lpm: Optional[float] = None
    operating_hours: float
    health_score: float = Field(..., ge=0, le=100)
    health_state: str
    anomaly_score: float = 0.0
    predicted_fault: str = "normal"
    sec_kwh_per_unit: Optional[float] = None
    recommended_action: str = ""
    timestamp: datetime


class CellState(BaseModel):
    """Cell-level aggregate state."""

    motors: list[MotorState]
    total_power_kw: float
    total_energy_kwh: float
    cell_production_units_h: float
    cell_sec_kwh_per_unit: Optional[float] = None
    sec_baseline: Optional[float] = None
    sec_ratio: Optional[float] = None
    timestamp: datetime


class AlertSchema(BaseModel):
    """Alert with reasoning."""

    id: int
    timestamp: datetime
    motor: str
    severity: str
    category: str
    message: str
    probable_cause: str
    recommended_action: str
    confidence: float
    acknowledged: bool = False


class HistoryQuery(BaseModel):
    """Query parameters for history endpoint."""

    from_: Optional[datetime] = Field(None, alias="from")
    to: Optional[datetime] = None
    limit: int = Field(1000, ge=1, le=10000)


class FaultInjectionRequest(BaseModel):
    """Request to inject a fault into the simulator."""

    motor: str
    fault_type: str
    duration_sec: int = Field(300, ge=10, le=3600)
    intensity: float = Field(1.0, ge=0.1, le=3.0)


class SimulateResetRequest(BaseModel):
    """Request to reset the simulator."""

    confirm: bool = False


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    motors_monitored: int
    uptime_sec: float
