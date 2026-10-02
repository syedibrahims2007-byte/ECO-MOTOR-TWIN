"""WebSocket endpoint for live data streaming."""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients
connected_clients: list[WebSocket] = []

# Latest twin state published by the background loop
_latest_state: dict[str, Any] = {}


def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN/inf with None so payloads are valid JSON."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def set_state(state: dict[str, Any]) -> None:
    """Store the latest twin state (called by the simulation loop)."""
    _latest_state.clear()
    _latest_state.update(_json_safe(state))


@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint pushing full twin state every second."""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("WebSocket client connected (%d total)", len(connected_clients))
    try:
        while True:
            state = await get_current_state()
            await websocket.send_text(json.dumps(state, default=str))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(connected_clients))
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        if websocket in connected_clients:
            connected_clients.remove(websocket)


async def get_current_state() -> dict[str, Any]:
    """Get the latest twin state published by the background task."""
    if _latest_state:
        return dict(_latest_state)
    return {
        "timestamp": datetime.now().isoformat(),
        "motors": [],
        "cell": {
            "total_power_kw": 0,
            "total_energy_kwh": 0,
            "cell_production_units_h": 0,
        },
        "status": "starting",
    }


async def broadcast_state(state: dict[str, Any]) -> None:
    """Broadcast state to all connected WebSocket clients."""
    set_state(state)
    if not connected_clients:
        return
    message = json.dumps(_json_safe(state), default=str)
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)
