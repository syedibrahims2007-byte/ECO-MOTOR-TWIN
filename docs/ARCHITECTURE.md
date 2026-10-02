# EcoMotorTwin – Architecture

## Source of Truth
`EcoMotorTwin_Four_Motor_Digital_Twin_Report.docx` – AI-Enabled Four-Motor Digital Twin for Real-Time Energy, Health and Predictive Maintenance.

## Report Summary (Key Requirements)

### Five-Layer Architecture (Report §5)
1. **Physical assets & sensors** – 4 motors (M1 conveyor, M2 pump, M3 compressor, M4 process machine) with electrical, thermal, mechanical sensors
2. **Data acquisition & edge processing** – Modbus/MQTT ingestion, validation, timestamping
3. **Digital Twin** – Live computational representation per motor + cell
4. **AI analytics** – Baseline learning, anomaly detection, fault classification, health index, trend analysis, cross-asset intelligence, energy analysis, recommendations
5. **Operator dashboard** – 3D twin view, charts, alerts, maintenance panel

### Four-Motor Configuration (Report §6)
| Motor | Role | Key Parameters |
|-------|------|----------------|
| M1 | Conveyor/drive | V, I, kW, RPM, vibration, temp |
| M2 | Pump/process flow | V, I, kW, pressure, flow, vibration, temp |
| M3 | Compressor/fan | V, I, kW, pressure, airflow, temp, vibration |
| M4 | Process machine | V, I, kW, RPM, vibration, temp |

### Cross-Asset Intelligence (Report §12)
- M1 speed → M2 load → M3 demand → M4 cycle
- Before raising motor-specific alert, check if other motors/production explain the deviation
- Example: M2 current up + M1 speed up + production up → process load change (suppress/downgrade)

### Energy Analysis (Report §13)
- SEC = Energy (kWh) / Production (units)
- Compare current SEC with learned baseline for similar production levels
- Distinguish "energy waste" from "higher production"

### AI/ML (Report §11)
- Time-series based, not isolated values
- Learn normal behaviour under different operating conditions
- Anomaly detection, fault classification, health index, trend/degradation
- **Do not claim exact failure date** without sufficient historical failure data

### Safety (Report §22)
- Use properly rated, isolated measurement equipment
- Never connect industrial mains directly to microcontroller ADC
- AI predictions are decision support, not replacement for certified protection

## Implemented Architecture

```
Simulator (or Modbus/MQTT)
  → Ingestion/validation → SQLite (readings, twin_state, alerts, health_history, energy_kpi)
  → Digital Twin engine (MotorTwin + CellTwin)
  → AI engine (features, baseline, anomaly, fault_classifier, health, trend, cross_asset, recommend)
  → FastAPI REST + WebSocket
  → Web dashboard (3D twin + charts + alerts)
```

### Module Mapping
| Report Section | Implementation |
|---------------|----------------|
| §5 Architecture | `backend/app/` layered structure |
| §6 Four motors | `config/config.yaml` motors section |
| §7 Parameters | `backend/app/simulator/simulator.py` |
| §8 Electrical | `simulator.py` power/PF model |
| §9 Mechanical/thermal | `simulator.py` thermal lag, vibration model |
| §10 Digital Twin | `backend/app/twin/motor_twin.py`, `cell_twin.py` |
| §11 AI/ML | `backend/app/ai/*.py` |
| §12 Cross-asset | `backend/app/ai/cross_asset.py` |
| §13 Energy/SEC | `backend/app/energy/sec.py` |
| §14 Dashboard | `frontend/` (Vite + Three.js + Chart.js) |
| §15 Scenario | `backend/tests/test_scenario.py` |
| §16 Hardware | `backend/app/ingest/source_modbus.py`, `source_mqtt.py` (stubs) |
| §17 Data flow | `backend/app/ingest/` → `core/db.py` → `twin/` → `ai/` → `api/` |
| §18 KPIs | `backend/app/energy/sec.py`, `api/routes.py` |
| §22 Safety | `README.md` safety note |
