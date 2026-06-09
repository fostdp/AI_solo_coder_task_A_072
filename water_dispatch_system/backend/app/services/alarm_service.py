from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sensor, SensorData, Alarm
from app.database import async_session
from app.config import ALARM_LEVEL1_DURATION_MINUTES, ALARM_LEVEL2_FLOW_DEVIATION_PERCENT


async def check_alarms() -> list:
    new_alarms = []
    async with async_session() as db:
        sensors_result = await db.execute(select(Sensor))
        sensors = sensors_result.scalars().all()

        for sensor in sensors:
            latest_stmt = (
                select(SensorData)
                .where(SensorData.sensor_id == sensor.id)
                .order_by(desc(SensorData.recorded_at))
                .limit(1)
            )
            latest_result = await db.execute(latest_stmt)
            latest = latest_result.scalar_one_or_none()
            if not latest:
                continue

            if sensor.sensor_type == "water_level":
                exceeds = False
                alarm_type = None
                threshold = None

                if latest.value > sensor.warning_upper:
                    exceeds = True
                    alarm_type = "level_high"
                    threshold = sensor.warning_upper
                elif latest.value < sensor.warning_lower:
                    exceeds = True
                    alarm_type = "level_low"
                    threshold = sensor.warning_lower

                if exceeds:
                    since = datetime.utcnow() - timedelta(minutes=15)
                    history_stmt = (
                        select(SensorData)
                        .where(
                            and_(
                                SensorData.sensor_id == sensor.id,
                                SensorData.recorded_at >= since,
                            )
                        )
                        .order_by(desc(SensorData.recorded_at))
                    )
                    history_result = await db.execute(history_stmt)
                    history_rows = history_result.scalars().all()

                    all_exceed = True
                    for row in history_rows:
                        if alarm_type == "level_high" and row.value <= sensor.warning_upper:
                            all_exceed = False
                            break
                        elif alarm_type == "level_low" and row.value >= sensor.warning_lower:
                            all_exceed = False
                            break

                    if all_exceed and len(history_rows) > 0:
                        earliest = history_rows[-1]
                        duration = (latest.recorded_at - earliest.recorded_at).total_seconds() / 60
                        if duration >= ALARM_LEVEL1_DURATION_MINUTES:
                            existing_stmt = select(Alarm).where(
                                and_(
                                    Alarm.source_type == "sensor",
                                    Alarm.source_id == sensor.id,
                                    Alarm.alarm_type == alarm_type,
                                    Alarm.status.in_(["active", "acknowledged"]),
                                )
                            )
                            existing_result = await db.execute(existing_stmt)
                            if not existing_result.scalar_one_or_none():
                                duration_int = int(duration)
                                direction = "超上限" if alarm_type == "level_high" else "低于下限"
                                alarm = Alarm(
                                    alarm_type=alarm_type,
                                    level=1,
                                    source_type="sensor",
                                    source_id=sensor.id,
                                    source_name=sensor.name,
                                    message=f"传感器 {sensor.name} 水位{direction}，持续 {duration_int} 分钟",
                                    value=latest.value,
                                    threshold=threshold,
                                    duration_minutes=duration_int,
                                    status="active",
                                )
                                db.add(alarm)
                                await db.flush()
                                new_alarms.append({
                                    "id": alarm.id,
                                    "alarm_type": alarm.alarm_type,
                                    "level": alarm.level,
                                    "source_type": alarm.source_type,
                                    "source_id": alarm.source_id,
                                    "source_name": alarm.source_name,
                                    "message": alarm.message,
                                    "value": float(alarm.value) if alarm.value else None,
                                    "threshold": float(alarm.threshold) if alarm.threshold else None,
                                    "duration_minutes": alarm.duration_minutes,
                                    "status": alarm.status,
                                    "created_at": alarm.created_at.isoformat() if alarm.created_at else None,
                                })

            elif sensor.sensor_type == "flow":
                if sensor.design_value and sensor.design_value != 0:
                    deviation = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100
                    if deviation > ALARM_LEVEL2_FLOW_DEVIATION_PERCENT:
                        existing_stmt = select(Alarm).where(
                            and_(
                                Alarm.source_type == "sensor",
                                Alarm.source_id == sensor.id,
                                Alarm.alarm_type == "flow_deviation",
                                Alarm.status.in_(["active", "acknowledged"]),
                            )
                        )
                        existing_result = await db.execute(existing_stmt)
                        if not existing_result.scalar_one_or_none():
                            alarm = Alarm(
                                alarm_type="flow_deviation",
                                level=2,
                                source_type="sensor",
                                source_id=sensor.id,
                                source_name=sensor.name,
                                message=f"传感器 {sensor.name} 流量偏差 {deviation:.1f}%，超过阈值 {ALARM_LEVEL2_FLOW_DEVIATION_PERCENT}%",
                                value=latest.value,
                                threshold=sensor.design_value,
                                duration_minutes=None,
                                status="active",
                            )
                            db.add(alarm)
                            await db.flush()
                            new_alarms.append({
                                "id": alarm.id,
                                "alarm_type": alarm.alarm_type,
                                "level": alarm.level,
                                "source_type": alarm.source_type,
                                "source_id": alarm.source_id,
                                "source_name": alarm.source_name,
                                "message": alarm.message,
                                "value": float(alarm.value) if alarm.value else None,
                                "threshold": float(alarm.threshold) if alarm.threshold else None,
                                "duration_minutes": alarm.duration_minutes,
                                "status": alarm.status,
                                "created_at": alarm.created_at.isoformat() if alarm.created_at else None,
                            })

        await db.commit()
    return new_alarms


async def resolve_alarm(alarm_id: int, db: AsyncSession):
    stmt = select(Alarm).where(Alarm.id == alarm_id)
    result = await db.execute(stmt)
    alarm = result.scalar_one_or_none()
    if alarm and alarm.status != "resolved":
        alarm.status = "resolved"
        alarm.resolved_at = datetime.utcnow()
        await db.commit()
        await db.refresh(alarm)
    return alarm


async def check_and_resolve_alarms(db: AsyncSession):
    active_stmt = select(Alarm).where(Alarm.status.in_(["active", "acknowledged"]))
    active_result = await db.execute(active_stmt)
    active_alarms = active_result.scalars().all()

    for alarm in active_alarms:
        if alarm.source_type != "sensor":
            continue

        sensor_stmt = select(Sensor).where(Sensor.id == alarm.source_id)
        sensor_result = await db.execute(sensor_stmt)
        sensor = sensor_result.scalar_one_or_none()
        if not sensor:
            continue

        latest_stmt = (
            select(SensorData)
            .where(SensorData.sensor_id == sensor.id)
            .order_by(desc(SensorData.recorded_at))
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()
        if not latest:
            continue

        condition_persists = False

        if alarm.alarm_type == "level_high":
            condition_persists = latest.value > sensor.warning_upper
        elif alarm.alarm_type == "level_low":
            condition_persists = latest.value < sensor.warning_lower
        elif alarm.alarm_type == "flow_deviation":
            if sensor.design_value and sensor.design_value != 0:
                deviation = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100
                condition_persists = deviation > ALARM_LEVEL2_FLOW_DEVIATION_PERCENT

        if not condition_persists:
            alarm.status = "resolved"
            alarm.resolved_at = datetime.utcnow()

    await db.commit()
