from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Sensor, SensorData
from app.schemas import DTUBatchIn, SensorDataOut, SensorHistoryOut, SensorOut
from app.services.dtu_receiver import receive_sensor_batch

router = APIRouter(tags=["dtu_receiver"])


@router.post("/data")
async def post_sensor_data(payload: DTUBatchIn, db: AsyncSession = Depends(get_db)):
    try:
        result = await receive_sensor_batch(payload, db)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return result


@router.get("/sensors", response_model=list[SensorOut])
async def list_sensors(db: AsyncSession = Depends(get_db)):
    stmt = select(Sensor, ST_X(Sensor.geom).label("lng"), ST_Y(Sensor.geom).label("lat"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for sensor, lng, lat in rows:
        latest_stmt = (
            select(SensorData)
            .where(SensorData.sensor_id == sensor.id)
            .order_by(desc(SensorData.recorded_at))
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()

        latest_value = None
        deviation_percent = None
        status_color = None
        if latest:
            latest_value = latest.value
            if sensor.design_value and float(sensor.design_value) != 0:
                deviation_percent = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100
                if deviation_percent < 10:
                    status_color = "green"
                elif deviation_percent <= 20:
                    status_color = "yellow"
                else:
                    status_color = "red"

        sensor_dict = {
            "id": sensor.id,
            "canal_id": sensor.canal_id,
            "section_id": sensor.section_id,
            "name": sensor.name,
            "code": sensor.code,
            "sensor_type": sensor.sensor_type,
            "design_value": sensor.design_value,
            "warning_upper": sensor.warning_upper,
            "warning_lower": sensor.warning_lower,
            "danger_upper": sensor.danger_upper,
            "danger_lower": sensor.danger_lower,
            "lng": float(lng) if lng else None,
            "lat": float(lat) if lat else None,
            "latest_value": latest_value,
            "deviation_percent": deviation_percent,
            "status_color": status_color,
        }
        out.append(SensorOut(**sensor_dict))
    return out


@router.get("/sensors/{sensor_id}/history", response_model=SensorHistoryOut)
async def sensor_history(
    sensor_id: int,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    sensor_stmt = (
        select(Sensor, ST_X(Sensor.geom).label("lng"), ST_Y(Sensor.geom).label("lat"))
        .where(Sensor.id == sensor_id)
    )
    sensor_result = await db.execute(sensor_stmt)
    sensor_row = sensor_result.first()
    if not sensor_row:
        raise HTTPException(status_code=404, detail="Sensor not found")

    sensor, lng, lat = sensor_row
    since = datetime.utcnow() - timedelta(hours=hours)

    data_stmt = (
        select(SensorData)
        .where(and_(SensorData.sensor_id == sensor_id, SensorData.recorded_at >= since))
        .order_by(SensorData.recorded_at)
    )
    data_result = await db.execute(data_stmt)
    data_rows = data_result.scalars().all()

    latest_stmt = (
        select(SensorData)
        .where(SensorData.sensor_id == sensor.id)
        .order_by(desc(SensorData.recorded_at))
        .limit(1)
    )
    latest_result = await db.execute(latest_stmt)
    latest = latest_result.scalar_one_or_none()
    latest_value = latest.value if latest else None
    deviation_percent = (
        abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100
        if latest and sensor.design_value and float(sensor.design_value) != 0
        else None
    )
    status_color = None
    if latest and deviation_percent is not None:
        if deviation_percent < 10:
            status_color = "green"
        elif deviation_percent <= 20:
            status_color = "yellow"
        else:
            status_color = "red"

    sensor_out = SensorOut(
        id=sensor.id,
        canal_id=sensor.canal_id,
        section_id=sensor.section_id,
        name=sensor.name,
        code=sensor.code,
        sensor_type=sensor.sensor_type,
        design_value=sensor.design_value,
        warning_upper=sensor.warning_upper,
        warning_lower=sensor.warning_lower,
        danger_upper=sensor.danger_upper,
        danger_lower=sensor.danger_lower,
        lng=float(lng) if lng else None,
        lat=float(lat) if lat else None,
        latest_value=latest_value,
        deviation_percent=deviation_percent,
        status_color=status_color,
    )

    return SensorHistoryOut(
        sensor=sensor_out,
        data=[
            SensorDataOut(id=d.id, sensor_id=d.sensor_id, value=d.value, recorded_at=d.recorded_at)
            for d in data_rows
        ],
        dispatch_history=[],
    )
