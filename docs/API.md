# EcoMotorTwin API Documentation

## REST Endpoints

### GET /api/health
Health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "motors_monitored": 4,
  "uptime_sec": 1234.5
}
```

### GET /api/motors
List all motors with configuration.

### GET /api/motors/{motor_id}
Get motor configuration and nominal values.

### GET /api/motors/{motor_id}/history
Get historical readings.

**Parameters:**
- `from` (datetime, optional): Start time
- `to` (datetime, optional): End time
- `limit` (int, default 1000): Max records

### GET /api/cell
Get cell-level state including all motors.

### GET /api/alerts
Get alert feed.

**Parameters:**
- `limit` (int, default 50): Max alerts
- `acknowledged` (bool, optional): Filter by status

### GET /api/energy/sec
Get energy and SEC data.

### POST /api/simulate/fault
Inject a fault for demo purposes.

**Body:**
```json
{
  "motor": "M2_Pump",
  "fault_type": "bearing_degradation",
  "duration_sec": 300,
  "intensity": 1.0
}
```

### POST /api/simulate/reset
Reset the simulator.

**Body:**
```json
{ "confirm": true }
```

## WebSocket

### WS /ws/live
Streams full twin state every second.

**Message format:**
```json
{
  "motors": [...],
  "cell": {
    "total_power_kw": 35.2,
    "cell_production_units_h": 520.0,
    "cell_sec_kwh_per_unit": 0.068
  },
  "timestamp": "2024-01-15T10:30:00"
}
```
