# EcoMotorTwin – AI-Enabled Four-Motor Digital Twin

Real-time energy, health and predictive maintenance for a four-motor production cell.

## Quick Start

```batch
run_all.bat
```

Then open http://localhost:5173 in your browser.

## Architecture

```
Simulator → Ingestion/validation → SQLite → Digital Twin → AI engine → FastAPI → Dashboard
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Project Structure

```
EcoMotorTwin/
├─ config/config.yaml          # All configuration
├─ backend/app/
│   ├─ main.py                 # FastAPI app
│   ├─ api/routes.py, ws.py    # REST + WebSocket
│   ├─ core/config.py, db.py   # Config loader, database
│   ├─ simulator/simulator.py  # Four-motor simulator
│   ├─ ingest/                 # Data sources (sim, Modbus, MQTT)
│   ├─ twin/                   # Digital Twin engine
│   ├─ ai/                     # ML models
│   ├─ energy/sec.py           # SEC analysis
│   └─ tests/                  # Pytest tests
├─ frontend/                   # Vite + Three.js + Chart.js
├─ data/                       # CSV + SQLite
├─ models_ml/                  # Trained models
└─ docs/                       # Documentation
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/motors` | List all motors |
| `GET /api/motors/{id}` | Motor details |
| `GET /api/motors/{id}/history` | Motor history |
| `GET /api/cell` | Cell state |
| `GET /api/alerts` | Alert feed |
| `GET /api/energy/sec` | Energy/SEC |
| `POST /api/simulate/fault` | Inject fault (demo) |
| `POST /api/simulate/reset` | Reset simulator |
| `WS /ws/live` | Live data stream |

## Safety Note

This system is for **decision support only**. It does not replace certified motor protection equipment. Never connect industrial mains directly to a microcontroller ADC. Use properly rated, isolated measurement devices.

## Manual Setup

```batch
# 1. Create venv
python -m venv .venv

# 2. Install dependencies
.venv\Scripts\pip install -r requirements.txt

# 3. Generate training data
.venv\Scripts\python -m backend.app.simulator.simulator

# 4. Train models
.venv\Scripts\python -m backend.app.ai.train

# 5. Start backend
.venv\Scripts\python -m backend.app.main

# 6. Start frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Testing

```batch
.venv\Scripts\python -m pytest backend/tests/ -v
```
