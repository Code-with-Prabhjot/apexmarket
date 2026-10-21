"""WebSocket telemetry hub: tracker snapshot at 10 Hz. Mount WITHOUT prefix -> /ws/telemetry"""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.progress_tracker import tracker

router = APIRouter()


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket, max_msgs: int | None = None):
    await ws.accept()
    sent = 0
    try:
        while max_msgs is None or sent < max_msgs:
            await ws.send_json(tracker.snapshot())
            sent += 1
            await asyncio.sleep(0.1)
        await ws.close()
    except WebSocketDisconnect:
        pass
