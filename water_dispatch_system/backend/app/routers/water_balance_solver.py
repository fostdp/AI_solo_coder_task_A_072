import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_AsGeoJSON

from app.services.water_balance_solver import calculate_dispatch_plan, calculate_water_balance
from app.database import get_db
from app.models import Canal, CanalSection, Sensor, SensorData, Gate, GateStatus, PumpStation, PumpStatus
from app.schemas import (
    DispatchRequest, DispatchPlanOut, DispatchCommandOut,
    WaterBalanceOut, KPIWaterBalanceOut, KPIWaterLevelOut,
    CanalOut, CanalSectionOut,
)

router = APIRouter(tags=["water-balance-solver"])


@router.post("/plan", response_model=DispatchPlanOut)
async def create_dispatch_plan(
    request: DispatchRequest, db: AsyncSession = Depends(get_db)
):
    plan = await calculate_dispatch_plan(
        request.canal_id, request.downstream_demand, db
    )

    commands = plan.get("commands", [])
    command_outs = []
    for idx, cmd in enumerate(commands):
        command_outs.append(DispatchCommandOut(
            id=-(idx + 1),
            plan_id=plan["plan_id"],
            target_type=cmd["target_type"],
            target_id=cmd["target_id"],
            target_name=cmd.get("target_name"),
            command_type=cmd["command_type"],
            command_value=cmd["command_value"],
            mqtt_topic=None,
            status="pending",
            created_at=None,
            sent_at=None,
            acked_at=None,
        ))

    wb = plan.get("water_balance", {})
    water_balance = WaterBalanceOut(
        canal_id=wb.get("canal_id", request.canal_id),
        canal_name=wb.get("canal_name", ""),
        total_inflow=wb.get("total_inflow", 0),
        total_outflow=wb.get("total_outflow", 0),
        total_storage_change=wb.get("total_storage_change", 0),
        total_loss=wb.get("total_loss", 0),
        balance_error=wb.get("balance_error", 0),
        balance_error_percent=wb.get("balance_error_percent", 0.0),
    )

    return DispatchPlanOut(
        plan_id=plan["plan_id"],
        canal_id=request.canal_id,
        commands=command_outs,
        water_balance=water_balance,
    )


@router.get("/balance/{canal_id}", response_model=WaterBalanceOut)
async def get_water_balance(canal_id: int, db: AsyncSession = Depends(get_db)):
    balance = await calculate_water_balance(canal_id, db)
    if not balance:
        raise HTTPException(status_code=404, detail="Canal not found")
    return WaterBalanceOut(**balance)


@router.get("/kpi/water-balance", response_model=KPIWaterBalanceOut)
async def kpi_water_balance(db: AsyncSession = Depends(get_db)):
    canals_result = await db.execute(select(Canal))
    canals = canals_result.scalars().all()

    canal_balances = []
    total_inflow = Decimal("0")
    total_outflow = Decimal("0")
    total_storage_change = Decimal("0")

    for canal in canals:
        balance = await calculate_water_balance(canal.id, db)
        if balance:
            wb = WaterBalanceOut(**balance)
            canal_balances.append(wb)
            total_inflow += wb.total_inflow
            total_outflow += wb.total_outflow
            total_storage_change += wb.total_storage_change

    return KPIWaterBalanceOut(
        canals=canal_balances,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        total_storage_change=total_storage_change,
    )


@router.get("/kpi/water-levels", response_model=list[KPIWaterLevelOut])
async def kpi_water_levels(db: AsyncSession = Depends(get_db)):
    stmt = select(CanalSection, Canal.name.label("canal_name")).join(
        Canal, CanalSection.canal_id == Canal.id
    )
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
            latest_stmt = (
                select(SensorData)
                .where(SensorData.sensor_id == sensor.id)
                .order_by(desc(SensorData.recorded_at))
                .limit(1)
            )
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


@router.get("/canals", response_model=list[CanalOut])
async def list_canals(db: AsyncSession = Depends(get_db)):
    stmt = select(Canal, ST_AsGeoJSON(Canal.geom).label("geom_geojson"))
    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for canal, geojson in rows:
        out.append(CanalOut(
            id=canal.id,
            name=canal.name,
            code=canal.code,
            length_km=canal.length_km,
            design_flow=canal.design_flow,
            geom_geojson=json.loads(geojson) if geojson else None,
        ))
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
        out.append(CanalSectionOut(
            id=section.id,
            canal_id=section.canal_id,
            name=section.name,
            code=section.code,
            start_km=section.start_km,
            end_km=section.end_km,
            design_water_level=section.design_water_level,
            design_flow=section.design_flow,
            storage_capacity=section.storage_capacity,
            geom_geojson=json.loads(geojson) if geojson else None,
        ))
    return out
