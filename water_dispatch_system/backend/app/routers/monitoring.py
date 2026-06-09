from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, desc, and_
from geoalchemy2.functions import ST_AsGeoJSON, ST_X, ST_Y
from app.database import get_db
from app.models import Canal, CanalSection, Sensor, SensorData, Gate, GateStatus, PumpStation, PumpStatus, DispatchCommand
from app.schemas import (
    CanalOut, CanalSectionOut, SensorOut, SensorDataOut, GateOut, GateStatusOut,
    PumpStationOut, PumpStatusOut, DTUBatchIn, KPIWaterBalanceOut, KPIWaterLevelOut,
    KPIPumpPowerOut, WaterBalanceOut, SensorHistoryOut, DispatchCommandOut,
)
from app.config import DTU_API_KEY
from datetime import datetime, timedelta
from decimal import Decimal
import json

router = APIRouter(tags=["monitoring"])


@router.get("/canals", response_model=list[CanalOut])
async def list_canals(db: AsyncSession = Depends(get_db)):
    stmt = select(Canal, ST_AsGeoJSON(Canal.geom).label("geom_geojson"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for canal, geojson in rows:
        canal_dict = {
            "id": canal.id,
            "name": canal.name,
            "code": canal.code,
            "length_km": canal.length_km,
            "design_flow": canal.design_flow,
            "geom_geojson": json.loads(geojson) if geojson else None,
        }
        out.append(CanalOut(**canal_dict))
    return out


@router.get("/canals/{canal_id}/sections", response_model=list[CanalSectionOut])
async def list_canal_sections(canal_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(CanalSection, ST_AsGeoJSON(CanalSection.geom).label("geom_geojson"))
        .where(CanalSection.canal_id == canal_id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for section, geojson in rows:
        section_dict = {
            "id": section.id,
            "canal_id": section.canal_id,
            "name": section.name,
            "code": section.code,
            "start_km": section.start_km,
            "end_km": section.end_km,
            "design_water_level": section.design_water_level,
            "design_flow": section.design_flow,
            "storage_capacity": section.storage_capacity,
            "geom_geojson": json.loads(geojson) if geojson else None,
        }
        out.append(CanalSectionOut(**section_dict))
    return out


def _calc_status_color(current_value: Decimal, design_value: Decimal) -> str:
    if design_value == 0:
        return "green"
    deviation = abs(float(current_value) - float(design_value)) / float(design_value) * 100
    if deviation < 10:
        return "green"
    elif deviation <= 20:
        return "yellow"
    else:
        return "red"


@router.get("/sensors", response_model=list[SensorOut])
async def list_sensors(db: AsyncSession = Depends(get_db)):
    stmt = select(Sensor, ST_X(Sensor.geom).label("lng"), ST_Y(Sensor.geom).label("lat"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for sensor, lng, lat in rows:
        latest_stmt = select(SensorData).where(SensorData.sensor_id == sensor.id).order_by(desc(SensorData.recorded_at)).limit(1)
        latest_result = await db.execute(latest_stmt)
        latest = latest_result.scalar_one_or_none()

        latest_value = None
        deviation_percent = None
        status_color = None
        if latest:
            latest_value = latest.value
            deviation_percent = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100 if sensor.design_value != 0 else 0.0
            status_color = _calc_status_color(latest.value, sensor.design_value)

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
async def sensor_history(sensor_id: int, hours: int = Query(24, ge=1, le=720), db: AsyncSession = Depends(get_db)):
    sensor_stmt = select(Sensor, ST_X(Sensor.geom).label("lng"), ST_Y(Sensor.geom).label("lat")).where(Sensor.id == sensor_id)
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

    latest_stmt = select(SensorData).where(SensorData.sensor_id == sensor.id).order_by(desc(SensorData.recorded_at)).limit(1)
    latest_result = await db.execute(latest_stmt)
    latest = latest_result.scalar_one_or_none()
    latest_value = latest.value if latest else None
    deviation_percent = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100 if latest and sensor.design_value != 0 else None
    status_color = _calc_status_color(latest.value, sensor.design_value) if latest else None

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

    dispatch_stmt = (
        select(DispatchCommand)
        .where(
            and_(
                DispatchCommand.target_type == "sensor",
                DispatchCommand.target_id == sensor_id,
                DispatchCommand.created_at >= since,
            )
        )
        .order_by(DispatchCommand.created_at)
    )
    dispatch_result = await db.execute(dispatch_stmt)
    dispatch_rows = dispatch_result.scalars().all()

    return SensorHistoryOut(
        sensor=sensor_out,
        data=[SensorDataOut(id=d.id, sensor_id=d.sensor_id, value=d.value, recorded_at=d.recorded_at) for d in data_rows],
        dispatch_history=[DispatchCommandOut.model_validate(d) for d in dispatch_rows],
    )


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
async def gate_history(gate_id: int, hours: int = Query(24, ge=1, le=720), db: AsyncSession = Depends(get_db)):
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
async def pump_station_history(station_id: int, hours: int = Query(24, ge=1, le=720), db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(PumpStatus)
        .where(and_(PumpStatus.pump_station_id == station_id, PumpStatus.recorded_at >= since))
        .order_by(PumpStatus.recorded_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PumpStatusOut(id=r.id, pump_station_id=r.pump_station_id, running_count=r.running_count, total_power=r.total_power, total_flow=r.total_flow, recorded_at=r.recorded_at) for r in rows]


@router.post("/dtu/data")
async def receive_dtu_data(payload: DTUBatchIn, db: AsyncSession = Depends(get_db)):
    if payload.api_key != DTU_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    inserted = 0
    for item in payload.data:
        sensor_stmt = select(Sensor).where(Sensor.code == item.sensor_code)
        sensor_result = await db.execute(sensor_stmt)
        sensor = sensor_result.scalar_one_or_none()
        if not sensor:
            continue

        new_data = SensorData(
            sensor_id=sensor.id,
            value=item.value,
            recorded_at=item.recorded_at,
        )
        db.add(new_data)
        inserted += 1

    await db.commit()
    return {"status": "ok", "inserted": inserted}


@router.get("/kpi/water-balance", response_model=KPIWaterBalanceOut)
async def kpi_water_balance(db: AsyncSession = Depends(get_db)):
    canals_result = await db.execute(select(Canal))
    canals = canals_result.scalars().all()

    canal_balances = []
    total_inflow = Decimal("0")
    total_outflow = Decimal("0")
    total_storage_change = Decimal("0")

    for canal in canals:
        inflow = Decimal("0")
        pump_stmt = select(PumpStation).where(PumpStation.canal_id == canal.id)
        pump_result = await db.execute(pump_stmt)
        pumps = pump_result.scalars().all()
        for pump in pumps:
            latest_stmt = select(PumpStatus).where(PumpStatus.pump_station_id == pump.id).order_by(desc(PumpStatus.recorded_at)).limit(1)
            latest_result = await db.execute(latest_stmt)
            latest = latest_result.scalar_one_or_none()
            if latest:
                inflow += latest.total_flow

        outflow = Decimal("0")
        gate_stmt = select(Gate).where(Gate.canal_id == canal.id)
        gate_result = await db.execute(gate_stmt)
        gates = gate_result.scalars().all()
        for gate in gates:
            latest_stmt = select(GateStatus).where(GateStatus.gate_id == gate.id).order_by(desc(GateStatus.recorded_at)).limit(1)
            latest_result = await db.execute(latest_stmt)
            latest = latest_result.scalar_one_or_none()
            if latest and latest.flow:
                outflow += latest.flow

        loss = inflow * Decimal("0.02")
        storage_change = inflow - outflow - loss
        balance_error = inflow - outflow - storage_change - loss
        balance_error_percent = float(balance_error) / float(inflow) * 100 if inflow != 0 else 0.0

        canal_balances.append(WaterBalanceOut(
            canal_id=canal.id,
            canal_name=canal.name,
            total_inflow=inflow,
            total_outflow=outflow,
            total_storage_change=storage_change,
            total_loss=loss,
            balance_error=balance_error,
            balance_error_percent=balance_error_percent,
        ))

        total_inflow += inflow
        total_outflow += outflow
        total_storage_change += storage_change

    return KPIWaterBalanceOut(
        canals=canal_balances,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        total_storage_change=total_storage_change,
    )


@router.get("/kpi/water-levels", response_model=list[KPIWaterLevelOut])
async def kpi_water_levels(db: AsyncSession = Depends(get_db)):
    stmt = select(CanalSection, Canal.name.label("canal_name")).join(Canal, CanalSection.canal_id == Canal.id)
    result = await db.execute(stmt)
    rows = result.all()

    out = []
    for section, canal_name in rows:
        sensor_stmt = select(Sensor).where(
            and_(Sensor.section_id == section.id, Sensor.sensor_type == "water_level")
        )
        sensor_result = await db.execute(sensor_stmt)
        sensor = sensor_result.scalar_one_or_none()

        current_level = None
        deviation_percent = None
        status_color = None

        if sensor:
            latest_stmt = select(SensorData).where(SensorData.sensor_id == sensor.id).order_by(desc(SensorData.recorded_at)).limit(1)
            latest_result = await db.execute(latest_stmt)
            latest = latest_result.scalar_one_or_none()
            if latest:
                current_level = latest.value
                if sensor.design_value != 0:
                    deviation_percent = abs(float(latest.value) - float(sensor.design_value)) / float(sensor.design_value) * 100
                    if deviation_percent < 10:
                        status_color = "green"
                    elif deviation_percent <= 20:
                        status_color = "yellow"
                    else:
                        status_color = "red"

        out.append(KPIWaterLevelOut(
            section_id=section.id,
            section_name=section.name,
            canal_name=canal_name,
            current_level=current_level,
            design_level=section.design_water_level,
            deviation_percent=deviation_percent,
            status_color=status_color,
        ))
    return out


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
