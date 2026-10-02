"""SQLite database setup and session management."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)
Base = declarative_base()


class Reading(Base):
    """Time-series sensor readings per motor."""

    __tablename__ = "readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    motor = Column(String(50), nullable=False, index=True)
    voltage_v = Column(Float)
    current_a = Column(Float)
    power_kw = Column(Float)
    temperature_c = Column(Float)
    rpm = Column(Float)
    vibration_g = Column(Float)
    energy_kwh = Column(Float)
    power_factor = Column(Float)
    pressure_bar = Column(Float, nullable=True)
    flow_lpm = Column(Float, nullable=True)
    operating_hours = Column(Float)
    fault_label = Column(String(50), default="normal")
    cell_production_units_h = Column(Float)


class TwinState(Base):
    """Digital twin state snapshot per motor."""

    __tablename__ = "twin_state"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    motor = Column(String(50), nullable=False, index=True)
    health_score = Column(Float)
    health_state = Column(String(20))
    anomaly_score = Column(Float)
    predicted_fault = Column(String(50))
    sec_kwh_per_unit = Column(Float)
    recommended_action = Column(Text)


class Alert(Base):
    """Generated alerts with reasoning."""

    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    motor = Column(String(50), nullable=False, index=True)
    severity = Column(String(20))
    category = Column(String(50))
    message = Column(Text)
    probable_cause = Column(Text)
    recommended_action = Column(Text)
    confidence = Column(Float)
    acknowledged = Column(Boolean, default=False)


class HealthHistory(Base):
    """Health index history per motor."""

    __tablename__ = "health_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    motor = Column(String(50), nullable=False, index=True)
    health_score = Column(Float)
    health_state = Column(String(20))


class EnergyKpi(Base):
    """Cell-level energy KPIs."""

    __tablename__ = "energy_kpi"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    total_power_kw = Column(Float)
    total_energy_kwh = Column(Float)
    cell_production_units_h = Column(Float)
    cell_sec_kwh_per_unit = Column(Float)
    sec_baseline = Column(Float)
    sec_ratio = Column(Float)


def get_engine(db_path: str | Path):
    """Create SQLAlchemy engine for SQLite."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return engine


def init_db(engine) -> None:
    """Create all tables."""
    Base.metadata.create_all(engine)
    logger.info("Database tables created")


def get_session_factory(engine):
    """Return a session factory bound to the engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
