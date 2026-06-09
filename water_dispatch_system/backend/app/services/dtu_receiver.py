from datetime import datetime

from sqlalchemy import select

from app.config import DTU_API_KEY
from app.database import async_session
from app.models import Sensor, SensorData
from app.schemas import DTUBatchIn
from app.services.redis_service import redis_pubsub


async def receive_sensor_batch(payload: DTUBatchIn, db) -> dict:
    if payload.api_key != DTU_API_KEY:
        raise PermissionError("Invalid API key")

    inserted = 0
    warnings = []
    readings = []

    for item in payload.data:
        sensor_stmt = select(Sensor).where(Sensor.code == item.sensor_code)
        sensor_result = await db.execute(sensor_stmt)
        sensor = sensor_result.scalar_one_or_none()
        if not sensor:
            continue

        exceeds_danger = False
        if sensor.danger_upper is not None and item.value > sensor.danger_upper:
            exceeds_danger = True
        if sensor.danger_lower is not None and item.value < sensor.danger_lower:
            exceeds_danger = True

        if exceeds_danger:
            warnings.append(sensor.code)

        new_data = SensorData(
            sensor_id=sensor.id,
            value=item.value,
            recorded_at=item.recorded_at,
        )
        db.add(new_data)
        inserted += 1

        readings.append({
            "sensor_id": sensor.id,
            "sensor_code": sensor.code,
            "value": float(item.value),
            "recorded_at": item.recorded_at.isoformat() if isinstance(item.recorded_at, datetime) else str(item.recorded_at),
            "sensor_type": sensor.sensor_type,
            "exceeds_danger": exceeds_danger,
        })

    await db.commit()

    for reading in readings:
        await redis_pubsub.publish("sensor_data", reading)

    return {"inserted": inserted, "warnings": warnings}
