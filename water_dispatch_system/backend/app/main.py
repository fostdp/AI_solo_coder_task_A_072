from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
from pathlib import Path

from app.database import engine
from app.services.redis_service import redis_pubsub
from app.services.command_dispatcher import command_dispatcher
from app.services.alarm_monitor import check_alarms, check_and_resolve_alarms, evaluate_sensor_data
from app.config import ALARM_CHECK_INTERVAL_SECONDS
from app.routers import dtu_receiver, water_balance_solver, command_dispatcher as cmd_router, alarm_monitor

app = FastAPI(title="跨流域调水工程调度监控系统")

app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dtu_receiver.router, prefix="/api/dtu", tags=["dtu_receiver"])
app.include_router(water_balance_solver.router, prefix="/api/water-balance", tags=["water_balance_solver"])
app.include_router(cmd_router.router, prefix="/api/dispatch", tags=["command_dispatcher"])
app.include_router(alarm_monitor.router, prefix="/api/alarm", tags=["alarm_monitor"])

static_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

connected_websockets: list[WebSocket] = []


@app.on_event("startup")
async def startup():
    await redis_pubsub.connect()

    redis_pubsub.register_handler("sensor_data", evaluate_sensor_data)
    redis_pubsub.register_handler("dispatch_command", command_dispatcher.on_dispatch_command)
    redis_pubsub.register_handler("alarm_event", _on_alarm_event)

    command_dispatcher.start()

    asyncio.create_task(alarm_checker_loop())


@app.on_event("shutdown")
async def shutdown():
    command_dispatcher.stop()
    await redis_pubsub.disconnect()
    await engine.dispose()


async def _on_alarm_event(data: dict):
    await broadcast({"type": "alarm", "data": data})


async def alarm_checker_loop():
    while True:
        try:
            alarms = await check_alarms()
            if alarms:
                await broadcast({"type": "alarm", "data": alarms})
            from app.database import async_session
            async with async_session() as db:
                await check_and_resolve_alarms(db)
        except Exception:
            pass
        await asyncio.sleep(ALARM_CHECK_INTERVAL_SECONDS)


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
