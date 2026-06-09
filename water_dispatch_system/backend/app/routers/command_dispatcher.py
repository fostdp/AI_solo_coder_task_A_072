from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y

from app.database import get_db
from app.models import DispatchCommand, Gate, GateStatus, PumpStation, PumpStatus
from app.schemas import (
    DispatchCommandOut,
    GateOut,
    GateStatusOut,
    PumpStationOut,
    PumpStatusOut,
    KPIPumpPowerOut,
)
from app.services.command_dispatcher import command_dispatcher
from decimal import Decimal

router = APIRouter(tags=["command-dispatcher"])


@router.get("/commands", response_model=list[DispatchCommandOut])
async def list_commands(
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=24)
    stmt = (
        select(DispatchCommand)
        .where(DispatchCommand.created_at >= since)
        .order_by(desc(DispatchCommand.created_at))
    )
    if status:
        stmt = stmt.where(DispatchCommand.status == status)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [DispatchCommandOut.model_validate(r) for r in rows]


@router.get("/commands/{command_id}", response_model=DispatchCommandOut)
async def get_command(command_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DispatchCommand).where(DispatchCommand.id == command_id)
    result = await db.execute(stmt)
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    return DispatchCommandOut.model_validate(cmd)


@router.post("/commands/{command_id}/cancel", response_model=DispatchCommandOut)
async def cancel_command(command_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DispatchCommand).where(DispatchCommand.id == command_id)
    result = await db.execute(stmt)
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending commands can be cancelled")
    cmd.status = "cancelled"
    await db.commit()
    await db.refresh(cmd)
    return DispatchCommandOut.model_validate(cmd)


@router.get("/history", response_model=list[DispatchCommandOut])
async def dispatch_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    stmt = (
        select(DispatchCommand)
        .order_by(desc(DispatchCommand.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [DispatchCommandOut.model_validate(r) for r in rows]


@router.get("/gates", response_model=list[GateOut])
async def list_gates(db: AsyncSession = Depends(get_db)):
    stmt = select(Gate, ST_X(Gate.geom).label("lng"), ST_Y(Gate.geom).label("lat"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for gate, lng, lat in rows:
        latest_stmt = select(GateStatus).where(GateStatus.gate_id == gate.id).order_by(desc(GateStatus.recorded_at)).limit(1)
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()
        latest_status = None
        if latest:
            latest_status = GateStatusOut(
                id=latest.id,
                gate_id=latest.gate_id,
                opening=latest.opening,
                flow=latest.flow,
                recorded_at=latest.recorded_at,
            )
        gate_dict = {
            "id": gate.id,
            "canal_id": gate.canal_id,
            "section_id": gate.section_id,
            "name": gate.name,
            "code": gate.code,
            "gate_type": gate.gate_type,
            "max_opening": gate.max_opening,
            "design_flow": gate.design_flow,
            "lng": float(lng) if lng else None,
            "lat": float(lat) if lat else None,
            "latest_status": latest_status,
        }
        out.append(GateOut(**gate_dict))
    return out


@router.get("/gates/{gate_id}/history", response_model=list[GateStatusOut])
async def gate_history(
    gate_id: int,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(GateStatus)
        .where(and_(GateStatus.gate_id == gate_id, GateStatus.recorded_at >= since))
        .order_by(GateStatus.recorded_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [GateStatusOut(id=r.id, gate_id=r.gate_id, opening=r.opening, flow=r.flow, recorded_at=r.recorded_at) for r in rows]


@router.get("/pump-stations", response_model=list[PumpStationOut])
async def list_pump_stations(db: AsyncSession = Depends(get_db)):
    stmt = select(PumpStation, ST_X(PumpStation.geom).label("lng"), ST_Y(PumpStation.geom).label("lat"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for station, lng, lat in rows:
        latest_stmt = select(PumpStatus).where(PumpStatus.pump_station_id == station.id).order_by(desc(PumpStatus.recorded_at)).limit(1)
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()
        latest_status = None
        if latest:
            latest_status = PumpStatusOut(
                id=latest.id,
                pump_station_id=latest.pump_station_id,
                running_count=latest.running_count,
                total_power=latest.total_power,
                total_flow=latest.total_flow,
                recorded_at=latest.recorded_at,
            )
        station_dict = {
            "id": station.id,
            "canal_id": station.canal_id,
            "section_id": station.section_id,
            "name": station.name,
            "code": station.code,
            "pump_count": station.pump_count,
            "single_pump_power": station.single_pump_power,
            "design_flow": station.design_flow,
            "head": station.head,
            "lng": float(lng) if lng else None,
            "lat": float(lat) if lat else None,
            "latest_status": latest_status,
        }
        out.append(PumpStationOut(**station_dict))
    return out


@router.get("/pump-stations/{station_id}/history", response_model=list[PumpStatusOut])
async def pump_station_history(
    station_id: int,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(PumpStatus)
        .where(and_(PumpStatus.pump_station_id == station_id, PumpStatus.recorded_at >= since))
        .order_by(PumpStatus.recorded_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PumpStatusOut(id=r.id, pump_station_id=r.pump_station_id, running_count=r.running_count, total_power=r.total_power, total_flow=r.total_flow, recorded_at=r.recorded_at) for r in rows]


@router.get("/kpi/pump-power", response_model=list[KPIPumpPowerOut])
async def kpi_pump_power(db: AsyncSession = Depends(get_db)):
    stmt = select(PumpStation)
    result = await db.execute(stmt)
    stations = result.scalars().all()

    out = []
    for station in stations:
        latest_stmt = select(PumpStatus).where(PumpStatus.pump_station_id == station.id).order_by(desc(PumpStatus.recorded_at)).limit(1)
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()

        running_count = 0
        total_power = Decimal("0")
        max_power = station.pump_count * station.single_pump_power
        load_percent = 0.0

        if latest:
            running_count = latest.running_count
            total_power = latest.total_power
            if max_power > 0:
                load_percent = float(total_power) / float(max_power) * 100

        out.append(KPIPumpPowerOut(
            station_id=station.id,
            station_name=station.name,
            running_count=running_count,
            total_pump_count=station.pump_count,
            total_power=total_power,
            max_power=max_power,
            load_percent=load_percent,
        ))
    return out
