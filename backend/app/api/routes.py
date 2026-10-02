"""REST API routes for EcoMotorTwin."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.core.schemas import (
    AlertSchema,
    CellState,
    FaultInjectionRequest,
    HealthResponse,
    HistoryQuery,
    MotorState,
    SimulateResetRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

START_TIME = time.time()


def _live_twin():
    """Return the live CellTwin from the running app, or None."""
    try:
        from backend.app import main as app_main

        return app_main.cell_twin
    except Exception:  # pragma: no cover — app not started (e.g. in tests)
        return None


def _live_source():
    """Return the live SimulatedSource from the running app, or None."""
    try:
        from backend.app import main as app_main

        return app_main.simulated_source
    except Exception:  # pragma: no cover
        return None


def get_engine():
    """Get database engine from app state."""
    from backend.app.core.db import get_engine, init_db
    from backend.app.core.config import load_config
    cfg = load_config()
    engine = get_engine(cfg["paths"]["db_path"])
    init_db(engine)
    return engine


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse, include_in_schema=True)
async def health_check() -> HealthResponse:
    """Health check endpoint (served at both /health and /api/health)."""
    from backend.app.core.config import load_config
    cfg = load_config()
    return HealthResponse(
        status="healthy",
        version=cfg["project"]["version"],
        motors_monitored=len(cfg["motors"]),
        uptime_sec=round(time.time() - START_TIME, 1),
    )


@router.get("/api/motors")
async def get_motors() -> list[dict[str, Any]]:
    """Get list of all motors with current state."""
    from backend.app.core.config import load_config
    cfg = load_config()
    motor_ids = list(cfg["motors"].keys())
    motors = []
    twin = _live_twin()
    for mid in motor_ids:
        mcfg = cfg["motors"][mid]
        item: dict[str, Any] = {
            "motor_id": mid,
            "role": mcfg["role"],
            "nominal": mcfg["nominal"],
            "limits": mcfg["limits"],
        }
        if twin is not None:
            live = twin.get_motor(mid)
            if live is not None:
                item["state"] = live.to_dict()
        motors.append(item)
    return motors


@router.get("/api/motors/{motor_id}")
async def get_motor(motor_id: str) -> dict[str, Any]:
    """Get current state of a specific motor (config + live twin state)."""
    from backend.app.core.config import load_config
    cfg = load_config()
    if motor_id not in cfg["motors"]:
        raise HTTPException(status_code=404, detail=f"Motor {motor_id} not found")
    mcfg = cfg["motors"][motor_id]
    result: dict[str, Any] = {
        "motor_id": motor_id,
        "role": mcfg["role"],
        "nominal": mcfg["nominal"],
        "limits": mcfg["limits"],
    }
    twin = _live_twin()
    if twin is not None:
        live = twin.get_motor(motor_id)
        if live is not None:
            result["state"] = live.to_dict()
    return result


@router.get("/api/motors/{motor_id}/history")
async def get_motor_history(
    motor_id: str,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    """Get historical readings for a motor."""
    from backend.app.core.db import get_session_factory, Reading
    from sqlalchemy import select

    engine = get_engine()
    Session = get_session_factory(engine)
    session = Session()

    try:
        stmt = select(Reading).where(Reading.motor == motor_id)
        if from_:
            stmt = stmt.where(Reading.timestamp >= from_)
        if to:
            stmt = stmt.where(Reading.timestamp <= to)
        stmt = stmt.order_by(Reading.timestamp.desc()).limit(limit)

        results = session.execute(stmt).scalars().all()
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "motor": r.motor,
                "voltage_v": r.voltage_v,
                "current_a": r.current_a,
                "power_kw": r.power_kw,
                "temperature_c": r.temperature_c,
                "rpm": r.rpm,
                "vibration_g": r.vibration_g,
                "energy_kwh": r.energy_kwh,
                "power_factor": r.power_factor,
                "pressure_bar": r.pressure_bar,
                "flow_lpm": r.flow_lpm,
                "operating_hours": r.operating_hours,
                "fault_label": r.fault_label,
                "cell_production_units_h": r.cell_production_units_h,
            }
            for r in results
        ]
    finally:
        session.close()


@router.get("/api/cell")
async def get_cell_state() -> dict[str, Any]:
    """Get current cell-level state (live twin if running, plus config)."""
    from backend.app.core.config import load_config
    cfg = load_config()
    result: dict[str, Any] = {
        "motor_ids": list(cfg["motors"].keys()),
        "process_chain": cfg.get("process_chain", []),
        "cell_config": cfg["cell"],
    }
    twin = _live_twin()
    if twin is not None:
        result["live"] = twin.to_dict()
    return result


@router.get("/api/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    acknowledged: bool | None = None,
) -> list[dict[str, Any]]:
    """Get alerts."""
    from backend.app.core.db import get_session_factory, Alert
    from sqlalchemy import select

    engine = get_engine()
    Session = get_session_factory(engine)
    session = Session()

    try:
        stmt = select(Alert)
        if acknowledged is not None:
            stmt = stmt.where(Alert.acknowledged == acknowledged)
        stmt = stmt.order_by(Alert.timestamp.desc()).limit(limit)

        results = session.execute(stmt).scalars().all()
        return [
            {
                "id": a.id,
                "timestamp": a.timestamp.isoformat(),
                "motor": a.motor,
                "severity": a.severity,
                "category": a.category,
                "message": a.message,
                "probable_cause": a.probable_cause,
                "recommended_action": a.recommended_action,
                "confidence": a.confidence,
                "acknowledged": a.acknowledged,
            }
            for a in results
        ]
    finally:
        session.close()


@router.get("/api/energy/sec")
async def get_energy_sec() -> dict[str, Any]:
    """Get energy and SEC data."""
    from backend.app.core.db import get_session_factory, EnergyKpi
    from sqlalchemy import select

    engine = get_engine()
    Session = get_session_factory(engine)
    session = Session()

    try:
        stmt = select(EnergyKpi).order_by(EnergyKpi.timestamp.desc()).limit(1)
        result = session.execute(stmt).scalars().first()
        if result:
            return {
                "timestamp": result.timestamp.isoformat(),
                "total_power_kw": result.total_power_kw,
                "total_energy_kwh": result.total_energy_kwh,
                "cell_production_units_h": result.cell_production_units_h,
                "cell_sec_kwh_per_unit": result.cell_sec_kwh_per_unit,
                "sec_baseline": result.sec_baseline,
                "sec_ratio": result.sec_ratio,
            }
        return {"error": "No energy data available"}
    finally:
        session.close()


@router.post("/api/simulate/fault")
async def inject_fault(request: FaultInjectionRequest) -> dict[str, Any]:
    """Inject a fault into the running simulator (demo).

    Use ``fault_type: "process_load_change"`` to raise load across the whole
    cell instead — that must NOT produce motor-specific alerts.
    """
    from backend.app.core.config import load_config
    cfg = load_config()
    if request.motor not in cfg["motors"]:
        raise HTTPException(status_code=404, detail=f"Motor {request.motor} not found")

    source = _live_source()
    if source is None:
        raise HTTPException(status_code=503, detail="Simulator not running")

    if request.fault_type == "process_load_change":
        increase = min(max(request.intensity * 0.25, 0.05), 0.5)
        entry = source.boost_process_load(
            duration_sec=request.duration_sec, increase=increase
        )
        logger.info("Process load boost started: +%d%% for %ds", increase * 100, request.duration_sec)
        return {
            "status": "accepted",
            "message": (
                f"Cell-wide load increase (+{increase * 100:.0f}%) for "
                f"{request.duration_sec}s — expect NO motor fault alerts"
            ),
            "entry": {k: str(v) for k, v in entry.items()},
        }

    valid_faults = {
        "bearing_degradation", "overheating", "overload", "imbalance", "voltage_sag",
    }
    if request.fault_type not in valid_faults:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown fault_type '{request.fault_type}'. Valid: {sorted(valid_faults)}",
        )

    entry = source.inject_fault(
        motor=request.motor,
        fault=request.fault_type,
        duration_sec=request.duration_sec,
        intensity=request.intensity,
    )
    logger.info(
        "Fault injection: %s on %s for %ds (intensity %.2f)",
        request.fault_type, request.motor, request.duration_sec, request.intensity,
    )
    return {
        "status": "accepted",
        "message": (
            f"Fault '{request.fault_type}' on {request.motor} for "
            f"{request.duration_sec}s"
        ),
        "entry": {k: str(v) for k, v in entry.items()},
    }


@router.post("/api/simulate/reset")
async def reset_simulator(request: SimulateResetRequest) -> dict[str, str]:
    """Reset the simulator (clears faults, boosts and internal state)."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Must confirm reset")
    source = _live_source()
    if source is None:
        raise HTTPException(status_code=503, detail="Simulator not running")
    source.reset()
    logger.info("Simulator reset")
    return {"status": "reset", "message": "Simulator reset complete"}
