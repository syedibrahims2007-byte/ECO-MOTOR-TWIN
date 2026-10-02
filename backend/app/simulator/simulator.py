"""Realistic four-motor digital twin simulator.

Generates physically-motivated time-series data with:
- Monotonic timestamps at configurable intervals
- Load profiles (shift pattern, ramp up/down, idle)
- Current proportional to load
- Temperature with thermal lag (first-order response)
- Vibration proportional to speed/load + noise
- RPM slip vs load
- Power = sqrt(3) * V * I * PF with load-dependent PF
- Energy = cumulative integral of power over time
- Cell-level coupling: M1 -> M2 -> M3 -> M4
- Fault injection with labels in defined windows
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.core.config import get_motor_ids, load_config

logger = logging.getLogger(__name__)


@dataclass
class MotorState:
    """Internal state of a simulated motor."""

    motor_id: str
    role: str
    load: float = 0.0
    voltage_v: float = 400.0
    current_a: float = 0.0
    power_kw: float = 0.0
    power_factor: float = 0.85
    temperature_c: float = 25.0
    rpm: float = 0.0
    vibration_g: float = 0.0
    energy_kwh: float = 0.0
    pressure_bar: float | None = None
    flow_lpm: float | None = None
    operating_hours: float = 0.0
    fault_label: str = "normal"
    fault_active: bool = False
    fault_ramp: float = 0.0
    # Fault multipliers/deltas applied inside _update_motor (neutral when no fault)
    fault_cur_mult: float = 1.0
    fault_temp_delta: float = 0.0
    fault_vib_delta: float = 0.0
    fault_volt_mult: float = 1.0
    fault_pf_delta: float = 0.0


@dataclass
class FaultWindow:
    """A scheduled fault injection window."""

    motor: str
    fault: str
    start_frac: float
    end_frac: float
    ramp_min: float


class FourMotorSimulator:
    """Simulates four coupled motors in a production cell."""

    def __init__(self, cfg: dict[str, Any] | None = None, seed: int | None = None):
        self.cfg = cfg or load_config()
        self.seed = seed if seed is not None else self.cfg["simulator"]["seed"]
        self.rng = np.random.default_rng(self.seed)
        self.motor_ids = get_motor_ids(self.cfg)
        self.motors: dict[str, MotorState] = {}
        self.cell_production = 0.0
        self.ambient_temp = self.cfg["cell"]["ambient_temp_c"]
        self.base_production = self.cfg["cell"]["base_production_units_h"]
        self.fault_windows: list[FaultWindow] = []
        self.process_load_window = self.cfg["simulator"].get("process_load_window", {})
        # Live (ad-hoc) injections for the demo API
        self.adhoc_faults: list[dict[str, Any]] = []
        self.load_boost: dict[str, Any] | None = None
        self._current_t_min: float = 0.0
        self._init_motors()
        self._init_fault_windows()

    # ------------------------------------------------------------------
    # Live injection API (used by POST /api/simulate/fault)
    # ------------------------------------------------------------------
    def inject_fault(
        self,
        motor: str,
        fault: str,
        duration_min: float,
        intensity: float = 1.0,
    ) -> dict[str, Any]:
        """Schedule an ad-hoc fault on a motor starting at the current sim time."""
        if motor not in self.motors:
            raise ValueError(f"Unknown motor: {motor}")
        ramp_min = max(0.2, min(1.0, duration_min / 4))
        entry = {
            "motor": motor,
            "fault": fault,
            "start": self._current_t_min,
            "end": self._current_t_min + duration_min,
            "ramp_min": ramp_min,
            "intensity": float(intensity),
        }
        self.adhoc_faults.append(entry)
        logger.info(
            "Ad-hoc fault injected: %s on %s for %.1f min (intensity %.2f)",
            fault, motor, duration_min, intensity,
        )
        return entry

    def boost_process_load(self, duration_min: float, increase: float = 0.25) -> dict[str, Any]:
        """Cell-wide load increase (process change — must NOT raise motor alerts)."""
        self.load_boost = {
            "start": self._current_t_min,
            "end": self._current_t_min + duration_min,
            "increase": float(increase),
        }
        logger.info(
            "Process load boost: +%.0f%% for %.1f min",
            increase * 100, duration_min,
        )
        return self.load_boost

    def clear_injections(self) -> None:
        """Remove all ad-hoc faults and load boosts."""
        self.adhoc_faults.clear()
        self.load_boost = None

    def _prune_injections(self, t_min: float) -> None:
        """Drop expired ad-hoc injections."""
        self.adhoc_faults = [f for f in self.adhoc_faults if f["end"] >= t_min]
        if self.load_boost and self.load_boost["end"] < t_min:
            self.load_boost = None

    def _init_motors(self) -> None:
        """Initialize motor states from config."""
        for mid in self.motor_ids:
            mcfg = self.cfg["motors"][mid]
            nom = mcfg["nominal"]
            self.motors[mid] = MotorState(
                motor_id=mid,
                role=mcfg["role"],
                voltage_v=nom["voltage_v"],
                temperature_c=self.ambient_temp + 10,
                rpm=0.0,
                pressure_bar=nom.get("pressure_bar"),
                flow_lpm=nom.get("flow_lpm"),
            )

    def _init_fault_windows(self) -> None:
        """Parse fault windows from config."""
        for fw in self.cfg["simulator"].get("fault_windows", []):
            self.fault_windows.append(FaultWindow(**fw))

    def _get_load_profile(self, t_min: float, motor_id: str) -> float:
        """Generate load profile: shift pattern with ramp up/down and idle."""
        # 3-shift pattern: 0-8h high, 8-16h medium, 16-24h low
        hour_of_day = (t_min / 60) % 24
        if 0 <= hour_of_day < 8:
            base_load = 0.85
        elif 8 <= hour_of_day < 16:
            base_load = 0.65
        else:
            base_load = 0.35

        # Add ramp at shift changes
        ramp_width = 30  # minutes
        for shift_start in [0, 8, 16]:
            shift_start_min = shift_start * 60
            if shift_start_min <= t_min % 1440 < shift_start_min + ramp_width:
                frac = (t_min % 1440 - shift_start_min) / ramp_width
                base_load *= 0.3 + 0.7 * frac

        # Motor-specific variation
        motor_idx = self.motor_ids.index(motor_id)
        variation = 0.05 * math.sin(2 * math.pi * t_min / (120 + motor_idx * 30))

        # Process load window (multi-motor, not a fault)
        plw = self.process_load_window
        if plw:
            total_min = self.cfg["simulator"]["history_days"] * 1440
            start_min = plw["start_frac"] * total_min
            end_min = plw["end_frac"] * total_min
            if start_min <= t_min <= end_min:
                base_load += plw.get("load_increase", 0.25)

        # Live ad-hoc process-load boost (demo)
        if self.load_boost and self.load_boost["start"] <= t_min <= self.load_boost["end"]:
            base_load += self.load_boost["increase"]

        return float(np.clip(base_load + variation, 0.05, 1.2))

    def _active_faults(self, motor_id: str, t_min: float) -> list[tuple[str, float, float]]:
        """Return [(fault_type, ramp_0_1, intensity)] active for this motor/time."""
        active: list[tuple[str, float, float]] = []
        total_min = self.cfg["simulator"]["history_days"] * 1440

        for fw in self.fault_windows:
            if fw.motor != motor_id:
                continue
            start_min = fw.start_frac * total_min
            end_min = fw.end_frac * total_min
            if start_min <= t_min <= end_min:
                if t_min >= start_min + fw.ramp_min:
                    ramp = 1.0
                else:
                    ramp = max(0.0, (t_min - start_min) / fw.ramp_min)
                active.append((fw.fault, ramp, 1.0))

        for af in self.adhoc_faults:
            if af["motor"] != motor_id:
                continue
            if af["start"] <= t_min <= af["end"]:
                if t_min >= af["start"] + af["ramp_min"]:
                    ramp = 1.0
                else:
                    ramp = max(0.0, (t_min - af["start"]) / af["ramp_min"])
                active.append((af["fault"], ramp, af["intensity"]))

        return active

    def _apply_fault_effects(self, state: MotorState, t_min: float, dt_min: float) -> None:
        """Compute fault multipliers for this step (idempotent — neutral when no fault).

        The factors are consumed by ``_update_motor`` so they compose with the
        nominal physics instead of fighting it.
        """
        active = self._active_faults(state.motor_id, t_min)

        # Reset to neutral every step — no compounding across timesteps.
        state.fault_cur_mult = 1.0
        state.fault_temp_delta = 0.0
        state.fault_vib_delta = 0.0
        state.fault_volt_mult = 1.0
        state.fault_pf_delta = 0.0

        if not active:
            state.fault_active = False
            state.fault_label = "normal"
            state.fault_ramp = 0.0
            return

        state.fault_active = True
        state.fault_label = active[0][0]
        state.fault_ramp = active[0][1]

        for fault, ramp, intensity in active:
            r = ramp * intensity
            if fault == "overload":
                state.fault_cur_mult *= 1.0 + 0.35 * r
                state.fault_temp_delta += 15.0 * r
                state.fault_pf_delta -= 0.05 * r
            elif fault == "overheating":
                state.fault_temp_delta += 20.0 * r
                state.fault_cur_mult *= 1.0 + 0.10 * r
            elif fault == "bearing_degradation":
                state.fault_vib_delta += 0.12 * r
                state.fault_temp_delta += 12.0 * r
                state.fault_cur_mult *= 1.0 + 0.08 * r
            elif fault == "imbalance":
                state.fault_vib_delta += 0.15 * r
                state.fault_cur_mult *= 1.0 + 0.12 * r
            elif fault == "voltage_sag":
                state.fault_volt_mult *= 1.0 - 0.15 * r
                state.fault_cur_mult *= 1.0 + 0.20 * r
                state.fault_pf_delta -= 0.08 * r

    def _update_motor(self, state: MotorState, load: float, dt_min: float) -> None:
        """Update a single motor's physical state."""
        mcfg = self.cfg["motors"][state.motor_id]
        nom = mcfg["nominal"]

        # Supply voltage (fault multiplier — neutral 1.0 when healthy)
        state.voltage_v = nom["voltage_v"] * state.fault_volt_mult

        # RPM with slip vs load
        nominal_rpm = nom["rpm"]
        slip = 0.02 * load  # 2% slip at full load
        state.rpm = nominal_rpm * (1 - slip) + self.rng.normal(0, 5)

        # Current proportional to load, scaled by fault multiplier
        state.current_a = (nom["current_a"] * load + self.rng.normal(0, 0.3)) * state.fault_cur_mult

        # Power factor varies with load (lower at partial load)
        state.power_factor = 0.75 + 0.15 * load + self.rng.normal(0, 0.01) + state.fault_pf_delta
        state.power_factor = float(np.clip(state.power_factor, 0.6, 0.98))

        # Power = sqrt(3) * V * I * PF / 1000 (kW)
        state.power_kw = (
            math.sqrt(3) * state.voltage_v * state.current_a * state.power_factor / 1000
        )

        # Temperature: first-order thermal lag toward a fault-shifted target
        target_temp = (
            self.ambient_temp + (nom["temperature_c"] - self.ambient_temp) * load
            + state.fault_temp_delta
        )
        tau = self.cfg["twin"]["thermal_time_constant_min"]
        alpha = 1 - math.exp(-dt_min / tau)
        state.temperature_c += alpha * (target_temp - state.temperature_c)
        state.temperature_c += self.rng.normal(0, 0.2)

        # Vibration proportional to speed/load + noise + fault delta
        base_vib = nom["vibration_g"]
        state.vibration_g = (
            base_vib * (0.5 + 0.5 * load) + self.rng.normal(0, 0.005) + state.fault_vib_delta
        )
        state.vibration_g = max(0.01, state.vibration_g)

        # Energy: cumulative integral of power over time
        state.energy_kwh += state.power_kw * (dt_min / 60)

        # Operating hours
        state.operating_hours += dt_min / 60

        # Pressure and flow for pump/compressor
        if mcfg.get("has_pressure") and state.pressure_bar is not None:
            state.pressure_bar = nom["pressure_bar"] * load + self.rng.normal(0, 0.05)
        if mcfg.get("has_flow") and state.flow_lpm is not None:
            state.flow_lpm = nom["flow_lpm"] * load + self.rng.normal(0, 2)

    def _update_cell_production(self) -> None:
        """Update cell production based on M4 cycles and M1 throughput."""
        m4 = self.motors.get("M4_ProcessMachine")
        m1 = self.motors.get("M1_Conveyor")
        if m4 and m1:
            # Production driven by M4 load and M1 throughput
            self.cell_production = self.base_production * m4.load * (0.5 + 0.5 * m1.load)
        else:
            self.cell_production = self.base_production

    def step(self, t_min: float, dt_min: float) -> dict[str, Any]:
        """Advance simulation by one time step, return readings dict."""
        self._current_t_min = t_min
        self._prune_injections(t_min)

        # Update loads with coupling
        loads: dict[str, float] = {}
        for mid in self.motor_ids:
            loads[mid] = self._get_load_profile(t_min, mid)

        # Apply process coupling: M1 -> M2 -> M3 -> M4
        chain = self.cfg.get("process_chain", [])
        for link in chain:
            from_m = link["from"]
            to_m = link["to"]
            coupling = link["coupling"]
            if from_m in loads and to_m in loads:
                loads[to_m] = loads[to_m] * (1 - coupling) + loads[from_m] * coupling

        # Update each motor: fault factors first, then nominal physics
        for mid, state in self.motors.items():
            state.load = loads[mid]
            self._apply_fault_effects(state, t_min, dt_min)
            self._update_motor(state, loads[mid], dt_min)

        self._update_cell_production()

        # Build readings
        readings = {}
        for mid, state in self.motors.items():
            readings[mid] = {
                "Motor": mid,
                "Voltage_V": round(state.voltage_v, 2),
                "Current_A": round(state.current_a, 2),
                "Power_kW": round(state.power_kw, 3),
                "Temperature_C": round(state.temperature_c, 2),
                "RPM": round(state.rpm, 1),
                "Vibration_g": round(state.vibration_g, 4),
                "Energy_kWh": round(state.energy_kwh, 4),
                "Power_Factor": round(state.power_factor, 3),
                "Pressure_bar": round(state.pressure_bar, 3) if state.pressure_bar else None,
                "Flow_lpm": round(state.flow_lpm, 2) if state.flow_lpm else None,
                "Operating_Hours": round(state.operating_hours, 2),
                "Fault_Label": state.fault_label,
                "Cell_Production_units_h": round(self.cell_production, 1),
                "Load": round(state.load, 3),
            }
        return readings

    def generate_history(self) -> pd.DataFrame:
        """Generate full training history as DataFrame."""
        days = self.cfg["simulator"]["history_days"]
        interval_sec = self.cfg["simulator"]["history_sample_interval_sec"]
        interval_min = interval_sec / 60
        total_min = days * 1440
        n_steps = int(total_min / interval_min)

        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=total_min)

        rows = []
        for i in range(n_steps):
            t_min = i * interval_min
            ts = start_time + timedelta(minutes=t_min)
            readings = self.step(t_min, interval_min)
            for mid, vals in readings.items():
                row = {"Timestamp": ts}
                row.update(vals)
                rows.append(row)

        df = pd.DataFrame(rows)
        logger.info("Generated %d rows of history data", len(df))
        return df

    def generate_live(self) -> pd.DataFrame:
        """Generate a short live dataset (last hour at 1 sample/sec)."""
        interval_sec = self.cfg["simulator"]["live_sample_interval_sec"]
        interval_min = interval_sec / 60
        n_steps = 3600  # 1 hour

        end_time = datetime.now()
        start_time = end_time - timedelta(seconds=n_steps * interval_sec)

        rows = []
        for i in range(n_steps):
            t_min = i * interval_min
            ts = start_time + timedelta(seconds=i * interval_sec)
            readings = self.step(t_min, interval_min)
            for mid, vals in readings.items():
                row = {"Timestamp": ts}
                row.update(vals)
                rows.append(row)

        df = pd.DataFrame(rows)
        return df

    def save_to_csv(self, df: pd.DataFrame, path: str | Path) -> None:
        """Save DataFrame to CSV."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        logger.info("Saved %d rows to %s", len(df), path)


def main() -> None:
    """CLI entry point for standalone simulation."""
    logging.basicConfig(level=logging.INFO)
    sim = FourMotorSimulator()
    df = sim.generate_history()
    csv_path = Path(sim.cfg["paths"]["csv_path"])
    sim.save_to_csv(df, csv_path)
    print(f"Generated {len(df)} rows -> {csv_path}")
    print(df.tail(8).to_string())


if __name__ == "__main__":
    main()
