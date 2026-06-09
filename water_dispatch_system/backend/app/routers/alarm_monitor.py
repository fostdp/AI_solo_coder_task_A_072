from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Alarm
from app.schemas import AlarmOut, AlarmAckRequest
from app.services.alarm_monitor import check_alarms, resolve_alarm

router = APIRouter(tags=["alarm_monitor"])


@router.get("/", response_model=list[AlarmOut])
async def list_alarms(
    status: str = Query(None),
    level: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Alarm).order_by(desc(Alarm.created_at))
    if status:
        stmt = stmt.where(Alarm.status == status)
    if level is not None:
        stmt = stmt.where(Alarm.level == level)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [AlarmOut.model_validate(r) for r in rows]


@router.get("/stats")
async def alarm_stats(db: AsyncSession = Depends(get_db)):
    level1_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.level == 1)
    level1_result = await db.execute(level1_count_stmt)
    level1_count = level1_result.scalar() or 0

    level2_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.level == 2)
    level2_result = await db.execute(level2_count_stmt)
    level2_count = level2_result.scalar() or 0

    active_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.status == "active")
    active_result = await db.execute(active_count_stmt)
    active_count = active_result.scalar() or 0

    acknowledged_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.status == "acknowledged")
    acknowledged_result = await db.execute(acknowledged_count_stmt)
    acknowledged_count = acknowledged_result.scalar() or 0

    resolved_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.status == "resolved")
    resolved_result = await db.execute(resolved_count_stmt)
    resolved_count = resolved_result.scalar() or 0

    since = datetime.utcnow() - timedelta(hours=24)
    recent_count_stmt = select(func.count()).select_from(Alarm).where(Alarm.created_at >= since)
    recent_result = await db.execute(recent_count_stmt)
    recent_count = recent_result.scalar() or 0

    return {
        "count_by_level": {1: level1_count, 2: level2_count},
        "count_by_status": {
            "active": active_count,
            "acknowledged": acknowledged_count,
            "resolved": resolved_count,
        },
        "recent_count": recent_count,
    }


@router.get("/{alarm_id}", response_model=AlarmOut)
async def get_alarm(alarm_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Alarm).where(Alarm.id == alarm_id)
    result = await db.execute(stmt)
    alarm = result.scalar_one_or_none()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return AlarmOut.model_validate(alarm)


@router.post("/acknowledge")
async def acknowledge_alarms(
    request: AlarmAckRequest, db: AsyncSession = Depends(get_db)
):
    now = datetime.utcnow()
    for alarm_id in request.alarm_ids:
        stmt = select(Alarm).where(Alarm.id == alarm_id)
        result = await db.execute(stmt)
        alarm = result.scalar_one_or_none()
        if alarm and alarm.status == "active":
            alarm.status = "acknowledged"
            alarm.acknowledged_at = now
    await db.commit()
    return {"status": "ok", "acknowledged": len(request.alarm_ids)}


@router.post("/{alarm_id}/resolve", response_model=AlarmOut)
async def resolve_alarm_endpoint(alarm_id: int, db: AsyncSession = Depends(get_db)):
    alarm = await resolve_alarm(alarm_id, db)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return AlarmOut.model_validate(alarm)
