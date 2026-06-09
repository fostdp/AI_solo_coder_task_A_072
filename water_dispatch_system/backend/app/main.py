from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
from pathlib import Path

from app.database import engine
from app.services.mqtt_service import mqtt_client
from app.services.alarm_service import check_alarms
from app.routers import monitoring, dispatch, alarm

app = FastAPI(title="跨流域调水工程调度监控系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
app.include_router(dispatch.router, prefix="/api/dispatch", tags=["dispatch"])
app.include_router(alarm.router, prefix="/api/alarm", tags=["alarm"])

static_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

connected_websockets: list[WebSocket] = []


@app.on_event("startup")
async def startup():
    mqtt_client.start()
    asyncio.create_task(alarm_checker_loop())


@app.on_event("shutdown")
async def shutdown():
    mqtt_client.stop()
    await engine.dispose()


async def alarm_checker_loop():
    while True:
        try:
            alarms = await check_alarms()
            if alarms:
                await broadcast({"type": "alarm", "data": alarms})
        except Exception:
            pass
        await asyncio.sleep(5)


async def broadcast(message: dict):
    disconnected = []
    for ws in connected_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_websockets.remove(ws)


@app.get("/")
async def serve_index():
    return FileResponse(static_dir / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                if msg_type == "sensor_data":
                    await broadcast({"type": "sensor_data", "data": message.get("data", {})})
                elif msg_type == "dispatch_status":
                    await broadcast({"type": "dispatch_status", "data": message.get("data", {})})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
