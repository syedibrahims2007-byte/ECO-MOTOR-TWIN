"""EcoMotorTwin FastAPI application.

Background task runs: simulator → ingest → twin → AI → DB → WebSocket broadcast.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import WebSocketRoute

from backend.app.ai.anomaly import AnomalyEngine
from backend.app.ai.baseline import BaselineEngine
from backend.app.ai.cross_asset import should_suppress_alert
from backend.app.ai.fault_classifier import FaultClassifier
from backend.app.ai.features import engineer_features
from backend.app.ai.health import compute_health_score
from backend.app.ai.recommend import generate_recommendation
from backend.app.ai.trend import compute_trend_slope
from backend.app.api.routes import router
from backend.app.api.ws import router as ws_router, set_state
from backend.app.core.config import load_config
from backend.app.core.db import (
    Alert,
    EnergyKpi,
    HealthHistory,
    Reading,
    get_engine,
    get_session_factory,
    init_db,
)
from backend.app.energy.sec import flag_energy_waste
from backend.app.ingest.source_sim import SimulatedSource
from backend.app.ingest.validator import validate_readings
from backend.app.twin.cell_twin import CellTwin

logger = logging.getLogger(__name__)

# Global state
cell_twin: CellTwin | None = None
simulated_source: SimulatedSource | None = None
start_time = time.time()

# AI state
baseline_engine: BaselineEngine | None = None
anomaly_engine: AnomalyEngine | None = None
classifier: FaultClassifier | None = None
ai_cfg: dict[str, Any] = {}
ai_buffers: dict[str, deque] = {}
health_history_pts: dict[str, deque] = {}
sec_baseline: float | None = None
sec_waste_threshold: float = 1.15
last_alerts: dict[tuple[str, str], datetime] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(value: Any) -> Any:
    """Convert NaN/inf to None for DB and JSON safety."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if value is not None and pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clean_readings(readings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return readings with NaN replaced by None."""
    return {mid: {k: _clean(v) for k, v in row.items()} for mid, row in readings.items()}


def _learn_sec_baseline(cfg: dict[str, Any]) -> float | None:
    """Learn cell SEC baseline (kW per unit/h) from normal-operation training data."""
    try:
        csv_path = Path(cfg["paths"]["csv_path"])
        if not csv_path.exists():
            return None
        df = pd.read_csv(
            csv_path,
            usecols=["Timestamp", "Power_kW", "Cell_Production_units_h", "Fault_Label"],
        )
        normal = df[df["Fault_Label"] == "normal"]
        cell = normal.groupby("Timestamp").agg(
            power=("Power_kW", "sum"),
            prod=("Cell_Production_units_h", "first"),
        )
        sec = (cell["power"] / cell["prod"].replace(0, np.nan)).dropna()
        sec = sec[(sec > 0) & (sec < 100)]
        if len(sec) == 0:
            return None
        logger.info("SEC baseline learned: %.4f kW per unit/h (%d samples)", sec.median(), len(sec))
        return float(sec.median())
    except Exception as e:  # pragma: no cover
        logger.warning("Could not learn SEC baseline: %s", e)
        return None


def _load_ai_models(cfg: dict[str, Any]) -> None:
    """Load trained models from disk (safe if missing)."""
    global baseline_engine, anomaly_engine, classifier
    models_dir = Path(cfg["paths"]["models_dir"])
    if not models_dir.exists():
        logger.warning("models_ml/ not found — run `python -m backend.app.ai.train`")
        return
    try:
        baseline_engine = BaselineEngine(models_dir)
        baseline_engine.load_all()
        anomaly_engine = AnomalyEngine(str(models_dir), cfg["ai"]["contamination"])
        anomaly_engine.load_all()
        clf_path = models_dir / "fault_classifier.joblib"
        classifier = FaultClassifier.load(clf_path) if clf_path.exists() else FaultClassifier()
        logger.info(
            "AI models loaded: %d baselines, %d anomaly detectors, classifier=%s",
            len(baseline_engine.baselines),
            len(anomaly_engine.detectors),
            "trained" if classifier.is_trained else "untrained",
        )
    except Exception as e:
        logger.error("Failed to load AI models: %s", e)
        baseline_engine = None
        anomaly_engine = None
        classifier = None


# ---------------------------------------------------------------------------
# AI step (per simulation tick)
# ---------------------------------------------------------------------------
def run_ai_step(
    readings: dict[str, dict[str, Any]],
    cell_production: float,
    cfg: dict[str, Any],
    twin: CellTwin,
) -> dict[str, Any]:
    """Run feature engineering + models + cross-asset + recommendations.

    Returns items for the caller to persist (DB writes stay in the loop).
    """
    out: dict[str, Any] = {
        "alerts": [],
        "health_rows": [],
        "energy_row": None,
        "waste": None,
        "suppressed": [],
    }
    now = datetime.now()

    # 1. Append to per-motor rolling buffers
    for mid, row in readings.items():
        entry = dict(row)
        entry["Timestamp"] = now
        if mid not in ai_buffers:
            ai_buffers[mid] = deque(maxlen=ai_cfg.get("ai_buffer_len", 20))
        ai_buffers[mid].append(entry)

    frames = [pd.DataFrame(list(buf)) for buf in ai_buffers.values() if buf]
    if not frames:
        return out
    df = pd.concat(frames, ignore_index=True)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])

    # 2. ML pipeline
    try:
        df = engineer_features(df, cfg["ai"]["rolling_windows"])
        if baseline_engine is not None:
            df = baseline_engine.predict_all(df)
        if anomaly_engine is not None:
            df = anomaly_engine.detect_all(df)
        if classifier is not None:
            df = classifier.predict(df)
    except Exception as e:
        logger.error("AI pipeline error: %s", e)
        return out

    latest = df.sort_values("Timestamp").groupby("Motor").tail(1)
    plain = {row["Motor"]: row.to_dict() for _, row in latest.iterrows()}

    nominals = {mid: cfg["motors"][mid]["nominal"] for mid in readings}
    process_chain = cfg.get("process_chain", [])
    base_production = cfg["cell"]["base_production_units_h"]
    healthy_th = cfg["twin"]["health_healthy_threshold"]
    warning_th = cfg["twin"]["health_warning_threshold"]
    alert_threshold = ai_cfg.get("alert_threshold", 0.5)
    cooldown_min = ai_cfg.get("alert_cooldown_min", 5)

    # 3. Per-motor: health, cross-asset, recommendation, alerts
    for mid, row in plain.items():
        twin_m = twin.get_motor(mid)
        if twin_m is None:
            continue

        score = float(_clean(row.get("anomaly_score")) or 0.0)
        predicted = str(row.get("predicted_fault") or "normal")
        confidence = float(_clean(row.get("fault_confidence")) or 0.0)
        temp_res = float(_clean(row.get("Temperature_C_residual")) or 0.0)
        vib_res = float(_clean(row.get("Vibration_g_residual")) or 0.0)
        curr_res = float(_clean(row.get("Current_A_residual")) or 0.0)

        # Cross-asset check (process load vs motor fault)
        suppression = should_suppress_alert(
            mid,
            score,
            plain,
            process_chain,
            cell_production,
            base_production,
            nominals=nominals,
        )
        if suppression["suppress"] or suppression["downgrade"]:
            out["suppressed"].append(
                {"motor": mid, "category": suppression["category"], "reason": suppression["reason"]}
            )

        # Health index (with trend from previous scores)
        hist = health_history_pts.setdefault(mid, deque(maxlen=cfg["ai"]["trend_window"]))
        trend = (
            float(compute_trend_slope(np.asarray(hist, dtype=float)))
            if len(hist) >= 3
            else 0.0
        )
        h_score, h_state = compute_health_score(
            score, temp_res, vib_res, curr_res, trend, healthy_th, warning_th
        )
        hist.append(h_score)

        twin_m.load = float(_clean(row.get("Load")) or 0.0)
        twin_m.update_anomaly(score, predicted)
        twin_m.update_health(h_score, h_state)
        if "Temperature_C_expected" in row:
            twin_m.update_baseline(
                float(_clean(row.get("Temperature_C_expected")) or 0.0),
                float(_clean(row.get("Vibration_g_expected")) or 0.0),
                float(_clean(row.get("Current_A_expected")) or 0.0),
            )

        # Recommendation
        rec = generate_recommendation(
            motor_id=mid,
            motor_role=twin_m.role,
            predicted_fault=predicted,
            health_score=h_score,
            health_state=h_state,
            anomaly_score=score,
            temp_residual=temp_res,
            vib_residual=vib_res,
            current_residual=curr_res,
            voltage_v=float(_clean(row.get("Voltage_V")) or 0.0),
            nominal_voltage=float(nominals.get(mid, {}).get("voltage_v", 400.0)),
            trend_info={"slope": trend},
            cross_asset_result=suppression,
        )
        twin_m.recommended_action = (
            f"{rec['recommended_action']} [urgency: {rec['urgency']}, "
            f"confidence: {rec['confidence']}]"
        )

        out["health_rows"].append(
            {
                "timestamp": now,
                "motor": mid,
                "health_score": h_score,
                "health_state": h_state,
            }
        )

        # Alert (deduplicated, never raised when cross-asset suppresses)
        if (
            score >= alert_threshold
            and predicted != "normal"
            and not suppression["suppress"]
        ):
            key = (mid, predicted)
            last = last_alerts.get(key)
            if last is None or (now - last).total_seconds() >= cooldown_min * 60:
                severity = {"Critical": "high", "Warning": "medium"}.get(h_state, "low")
                if suppression["downgrade"]:
                    severity = "low"
                out["alerts"].append(
                    {
                        "timestamp": now,
                        "motor": mid,
                        "severity": severity,
                        "category": "motor_fault",
                        "message": (
                            f"{mid}: {predicted} detected "
                            f"(anomaly {score:.2f}, health {h_score:.0f}/100)"
                        ),
                        "probable_cause": rec["probable_cause"]
                        + (f" — evidence: {rec['evidence']}" if rec.get("evidence") else ""),
                        "recommended_action": rec["recommended_action"],
                        "confidence": confidence if confidence > 0 else 0.5,
                        "acknowledged": False,
                    }
                )
                last_alerts[key] = now
                logger.warning(
                    "ALERT %s on %s: %s (score=%.2f, health=%.0f)",
                    severity, mid, predicted, score, h_score,
                )

    # 4. Cell energy KPI
    cell_dict = twin.to_dict()
    total_power = float(cell_dict.get("total_power_kw") or 0.0)
    production = float(cell_production or 0.0)
    sec_now = (total_power / production) if production > 0 else None
    ratio = (sec_now / sec_baseline) if (sec_now and sec_baseline) else None
    if sec_now is not None and sec_baseline:
        out["waste"] = flag_energy_waste(
            sec_now, sec_baseline, cfg["energy"]["sec_waste_threshold"]
        )
    out["energy_row"] = {
        "timestamp": now,
        "total_power_kw": total_power,
        "total_energy_kwh": float(cell_dict.get("total_energy_kwh") or 0.0),
        "cell_production_units_h": production,
        "cell_sec_kwh_per_unit": sec_now,
        "sec_baseline": sec_baseline,
        "sec_ratio": ratio,
    }
    return out


def build_payload(twin: CellTwin, ai_out: dict[str, Any]) -> dict[str, Any]:
    """Assemble the WebSocket/REST payload expected by the frontend."""
    cell_dict = twin.to_dict()
    return {
        "timestamp": cell_dict.get("timestamp") or datetime.now().isoformat(),
        "motors": cell_dict.get("motors", []),
        "cell": {
            "total_power_kw": cell_dict.get("total_power_kw", 0.0),
            "total_energy_kwh": cell_dict.get("total_energy_kwh", 0.0),
            "cell_production_units_h": cell_dict.get("cell_production_units_h", 0.0),
            "cell_sec_kwh_per_unit": cell_dict.get("cell_sec_kwh_per_unit"),
            "sec_baseline": cell_dict.get("sec_baseline"),
            "sec_ratio": cell_dict.get("sec_ratio"),
            "sec_waste": (ai_out.get("waste") or {}).get("reason"),
        },
        "ai": {
            "models_loaded": baseline_engine is not None,
            "alerts_this_tick": len(ai_out.get("alerts", [])),
            "suppressed_this_tick": len(ai_out.get("suppressed", [])),
        },
    }


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager — starts background simulation task."""
    global cell_twin, simulated_source, ai_cfg, sec_baseline, sec_waste_threshold

    cfg = load_config()
    logger.info("Starting EcoMotorTwin backend v%s", cfg["project"]["version"])

    # Initialize database
    engine = get_engine(cfg["paths"]["db_path"])
    init_db(engine)

    # Initialize cell twin
    motor_ids = list(cfg["motors"].keys())
    motor_roles = {mid: cfg["motors"][mid]["role"] for mid in motor_ids}
    cell_twin = CellTwin(motor_ids, motor_roles)
    if sec_baseline:
        cell_twin.set_sec_baseline(sec_baseline)

    # AI configuration + rolling buffers
    ai_cfg = dict(cfg["ai"])
    sec_waste_threshold = cfg["energy"]["sec_waste_threshold"]
    for mid in motor_ids:
        ai_buffers[mid] = deque(maxlen=ai_cfg.get("ai_buffer_len", 20))
        health_history_pts[mid] = deque(maxlen=cfg["ai"]["trend_window"])

    # Load trained models + SEC baseline
    _load_ai_models(cfg)
    sec_baseline = _learn_sec_baseline(cfg)
    if cell_twin and sec_baseline:
        cell_twin.set_sec_baseline(sec_baseline)

    # Initialize simulator
    simulated_source = SimulatedSource(cfg)
    simulated_source.connect()

    # Start background task
    task = asyncio.create_task(simulation_loop(cfg))
    logger.info("Background simulation loop started")

    yield

    # Cleanup
    task.cancel()
    simulated_source.disconnect()
    logger.info("EcoMotorTwin backend stopped")


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------
def _register_routes(app: FastAPI, source_router) -> None:
    """Register HTTP + WebSocket routes from an APIRouter.

    FastAPI 0.142.2's ``include_router`` wraps routes in a lazy
    ``_IncludedRouter`` object; expanding explicitly keeps routing
    deterministic and OpenAPI complete.
    """
    for route in source_router.routes:
        if isinstance(route, WebSocketRoute):
            app.add_api_websocket_route(route.path, route.endpoint)
        else:
            app.add_api_route(
                path=route.path,
                endpoint=route.endpoint,
                methods=sorted(route.methods) if route.methods else ["GET"],
                name=route.name,
                response_model=getattr(route, "response_model", None),
                tags=getattr(route, "tags", None) or None,
                include_in_schema=getattr(route, "include_in_schema", True),
            )


app = FastAPI(
    title="EcoMotorTwin",
    description="AI-Enabled Four-Motor Digital Twin for Real-Time Energy, Health and Predictive Maintenance",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST + WebSocket routes
_register_routes(app, router)
_register_routes(app, ws_router)


# ---------------------------------------------------------------------------
# Background loop: simulator → ingest → twin → AI → DB → WebSocket
# ---------------------------------------------------------------------------
async def simulation_loop(cfg: dict[str, Any]) -> None:
    """Background loop: simulator → ingest → twin → AI → DB."""
    global cell_twin, simulated_source

    engine = get_engine(cfg["paths"]["db_path"])
    Session = get_session_factory(engine)
    health_every = ai_cfg.get("health_history_write_every_n", 10)
    energy_every = ai_cfg.get("energy_kpi_write_every_n", 10)
    tick = 0

    while True:
        try:
            # 1. Read from simulator
            df = simulated_source.read()
            if df.empty:
                await asyncio.sleep(1)
                continue

            # 2. Validate
            df = validate_readings(df)

            # 3. Update twin
            readings: dict[str, dict[str, Any]] = {}
            cell_production = 0.0
            for _, row in df.iterrows():
                mid = row["Motor"]
                readings[mid] = row.to_dict()
                cell_production = float(_clean(row.get("Cell_Production_units_h")) or 0.0)
            readings = _clean_readings(readings)

            if cell_twin:
                cell_twin.update(readings, cell_production)

            # 4. AI: features → models → cross-asset → recommendations
            ai_out = (
                run_ai_step(readings, cell_production, cfg, cell_twin)
                if cell_twin
                else {"alerts": [], "health_rows": [], "energy_row": None, "waste": None, "suppressed": []}
            )

            # 5. Persist
            session = Session()
            try:
                ts = readings[next(iter(readings))].get("Timestamp") or datetime.now()
                for mid, r in readings.items():
                    session.add(
                        Reading(
                            timestamp=r.get("Timestamp") or ts,
                            motor=mid,
                            voltage_v=r.get("Voltage_V"),
                            current_a=r.get("Current_A"),
                            power_kw=r.get("Power_kW"),
                            temperature_c=r.get("Temperature_C"),
                            rpm=r.get("RPM"),
                            vibration_g=r.get("Vibration_g"),
                            energy_kwh=r.get("Energy_kWh"),
                            power_factor=r.get("Power_Factor"),
                            pressure_bar=r.get("Pressure_bar"),
                            flow_lpm=r.get("Flow_lpm"),
                            operating_hours=r.get("Operating_Hours"),
                            fault_label=r.get("Fault_Label", "normal"),
                            cell_production_units_h=r.get("Cell_Production_units_h"),
                        )
                    )
                for alert in ai_out["alerts"]:
                    session.add(Alert(**alert))
                if tick % health_every == 0:
                    for hr in ai_out["health_rows"]:
                        session.add(HealthHistory(**hr))
                if tick % energy_every == 0 and ai_out["energy_row"]:
                    session.add(EnergyKpi(**ai_out["energy_row"]))
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error("DB write error: %s", e)
            finally:
                session.close()

            # 6. Publish state for WebSocket clients
            if cell_twin:
                set_state(build_payload(cell_twin, ai_out))

            tick += 1
            await asyncio.sleep(cfg["api"]["ws_interval_sec"])

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Simulation loop error: %s", e, exc_info=True)
            await asyncio.sleep(5)


def main() -> None:
    """Run the FastAPI application."""
    import uvicorn
    cfg = load_config()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "backend.app.main:app",
        host=cfg["api"]["host"],
        port=cfg["api"]["port"],
        reload=False,
    )


if __name__ == "__main__":
    main()
