import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Canal, CanalSection, Sensor, SensorData,
    Gate, GateStatus, PumpStation, PumpStatus, DispatchCommand,
)
from app.database import async_session
from app.services.mqtt_service import mqtt_client
from app.config import DISPATCH_TOPIC_PREFIX


async def calculate_dispatch_plan(
    canal_id: int, downstream_demand: Decimal, db: AsyncSession
) -> dict:
    plan_id = str(uuid.uuid4())

    canal_stmt = select(Canal).where(Canal.id == canal_id)
    canal_result = await db.execute(canal_stmt)
    canal = canal_result.scalar_one_or_none()
    if not canal:
        return {"plan_id": plan_id, "commands": [], "water_balance": {}}

    sections_stmt = (
        select(CanalSection)
        .where(CanalSection.canal_id == canal_id)
        .order_by(CanalSection.start_km)
    )
    sections_result = await db.execute(sections_stmt)
    sections = sections_result.scalars().all()

    if not sections:
        return {"plan_id": plan_id, "commands": [], "water_balance": {}}

    commands = []
    total_inflow = Decimal("0")
    total_outflow = Decimal("0")
    total_storage_change = Decimal("0")

    num_sections = len(sections)
    demand_per_section = downstream_demand / Decimal(num_sections) if num_sections > 0 else Decimal("0")

    for section in sections:
        water_level_stmt = (
            select(SensorData.value)
            .join(Sensor, SensorData.sensor_id == Sensor.id)
            .where(
                and_(
                    Sensor.section_id == section.id,
                    Sensor.sensor_type == "water_level",
                )
            )
            .order_by(desc(SensorData.recorded_at))
            .limit(1)
        )
        water_level_result = await db.execute(water_level_stmt)
        current_water_level = water_level_result.scalar_one_or_none() or Decimal("0")

        if section.design_water_level and section.design_water_level > 0:
            level_ratio = current_water_level / section.design_water_level
        else:
            level_ratio = Decimal("0")
        current_storage = level_ratio * section.storage_capacity

        pump_stmt = select(PumpStation).where(PumpStation.section_id == section.id)
        pump_result = await db.execute(pump_stmt)
        pumps = pump_result.scalars().all()

        section_inflow = Decimal("0")
        running_pumps = 0
        for pump in pumps:
            status_stmt = (
                select(PumpStatus)
                .where(PumpStatus.pump_station_id == pump.id)
                .order_by(desc(PumpStatus.recorded_at))
                .limit(1)
            )
            status_result = await db.execute(status_stmt)
            status = status_result.scalar_one_or_none()
            if status:
                section_inflow += status.total_flow
                running_pumps += status.running_count
            else:
                running_pumps = 0

        gate_stmt = select(Gate).where(Gate.section_id == section.id)
        gate_result = await db.execute(gate_stmt)
        gates = gate_result.scalars().all()

        section_outflow = Decimal("0")
        for gate in gates:
            status_stmt = (
                select(GateStatus)
                .where(GateStatus.gate_id == gate.id)
                .order_by(desc(GateStatus.recorded_at))
                .limit(1)
            )
            status_result = await db.execute(status_stmt)
            status = status_result.scalar_one_or_none()
            if status and status.flow:
                section_outflow += status.flow

        total_inflow += section_inflow
        total_outflow += section_outflow

        ds = section_inflow - section_outflow
        total_storage_change += ds

        required_flow = demand_per_section * (section.design_flow / canal.design_flow) if canal.design_flow > 0 else demand_per_section
        required_flow = required_flow.quantize(Decimal("0.01"))

        for gate in gates:
            opening = Decimal("0")
            if gate.design_flow and gate.design_flow > 0:
                opening = (required_flow / gate.design_flow) * Decimal("100")
            opening = max(Decimal("0"), min(Decimal("100"), opening))
            opening = opening.quantize(Decimal("0.01"))

            commands.append({
                "target_type": "gate",
                "target_id": gate.id,
                "target_name": gate.name,
                "command_type": "set_opening",
                "command_value": opening,
            })

        for pump in pumps:
            single_pump_flow = pump.design_flow / pump.pump_count if pump.pump_count > 0 else pump.design_flow
            if single_pump_flow == 0:
                single_pump_flow = pump.design_flow

            current_running = running_pumps
            needed_flow = required_flow
            current_capacity = Decimal(current_running) * single_pump_flow

            if needed_flow > current_capacity:
                additional = int((needed_flow - current_capacity) / single_pump_flow) + 1
                new_running = min(current_running + additional, pump.pump_count)
                if new_running > current_running:
                    commands.append({
                        "target_type": "pump",
                        "target_id": pump.id,
                        "target_name": pump.name,
                        "command_type": "start_pumps",
                        "command_value": Decimal(new_running - current_running),
                    })
            elif needed_flow < current_capacity * Decimal("0.8"):
                excess = int((current_capacity - needed_flow) / single_pump_flow)
                stop_count = min(excess, current_running)
                if stop_count > 0:
                    commands.append({
                        "target_type": "pump",
                        "target_id": pump.id,
                        "target_name": pump.name,
                        "command_type": "stop_pumps",
                        "command_value": Decimal(stop_count),
                    })

    total_loss = total_inflow * Decimal("0.02")
    balance_error = total_inflow - total_outflow - total_storage_change - total_loss
    balance_error_percent = (
        float(balance_error) / float(total_inflow) * 100
        if total_inflow != 0
        else 0.0
    )

    water_balance = {
        "canal_id": canal_id,
        "canal_name": canal.name,
        "total_inflow": total_inflow.quantize(Decimal("0.01")),
        "total_outflow": total_outflow.quantize(Decimal("0.01")),
        "total_storage_change": total_storage_change.quantize(Decimal("0.01")),
        "total_loss": total_loss.quantize(Decimal("0.01")),
        "balance_error": balance_error.quantize(Decimal("0.01")),
        "balance_error_percent": balance_error_percent,
    }

    return {
        "plan_id": plan_id,
        "canal_id": canal_id,
        "commands": commands,
        "water_balance": water_balance,
    }


async def execute_dispatch_plan(plan: dict) -> list:
    plan_id = plan["plan_id"]
    commands = plan.get("commands", [])

    saved_commands = []
    async with async_session() as session:
        for cmd in commands:
            topic = f"{DISPATCH_TOPIC_PREFIX}/{cmd['target_type']}/{cmd['target_id']}"
            payload = {
                "plan_id": plan_id,
                "target_type": cmd["target_type"],
                "target_id": cmd["target_id"],
                "command_type": cmd["command_type"],
                "command_value": float(cmd["command_value"]),
            }

            db_cmd = DispatchCommand(
                plan_id=plan_id,
                target_type=cmd["target_type"],
                target_id=cmd["target_id"],
                target_name=cmd.get("target_name"),
                command_type=cmd["command_type"],
                command_value=cmd["command_value"],
                mqtt_topic=topic,
                status="pending",
            )
            session.add(db_cmd)
            await session.flush()

            mqtt_client.publish(topic, payload)

            db_cmd.status = "sent"
            db_cmd.sent_at = datetime.utcnow()

            saved_commands.append(db_cmd)

        await session.commit()
        for c in saved_commands:
            await session.refresh(c)

    return saved_commands


async def calculate_water_balance(
    canal_id: int, db: AsyncSession
) -> dict:
    canal_stmt = select(Canal).where(Canal.id == canal_id)
    canal_result = await db.execute(canal_stmt)
    canal = canal_result.scalar_one_or_none()
    if not canal:
        return {}

    total_inflow = Decimal("0")
    pump_stmt = select(PumpStation).where(PumpStation.canal_id == canal_id)
    pump_result = await db.execute(pump_stmt)
    pumps = pump_result.scalars().all()
    for pump in pumps:
        status_stmt = (
            select(PumpStatus)
            .where(PumpStatus.pump_station_id == pump.id)
            .order_by(desc(PumpStatus.recorded_at))
            .limit(1)
        )
        status_result = await db.execute(status_stmt)
        status = status_result.scalar_one_or_none()
        if status:
            total_inflow += status.total_flow

    total_outflow = Decimal("0")
    gate_stmt = select(Gate).where(Gate.canal_id == canal_id)
    gate_result = await db.execute(gate_stmt)
    gates = gate_result.scalars().all()
    for gate in gates:
        status_stmt = (
            select(GateStatus)
            .where(GateStatus.gate_id == gate.id)
            .order_by(desc(GateStatus.recorded_at))
            .limit(1)
        )
        status_result = await db.execute(status_stmt)
        status = status_result.scalar_one_or_none()
        if status and status.flow:
            total_outflow += status.flow

    total_loss = total_inflow * Decimal("0.02")
    total_storage_change = total_inflow - total_outflow - total_loss
    balance_error = total_inflow - total_outflow - total_storage_change - total_loss
    balance_error_percent = (
        float(balance_error) / float(total_inflow) * 100
        if total_inflow != 0
        else 0.0
    )

    return {
        "canal_id": canal_id,
        "canal_name": canal.name,
        "total_inflow": total_inflow.quantize(Decimal("0.01")),
        "total_outflow": total_outflow.quantize(Decimal("0.01")),
        "total_storage_change": total_storage_change.quantize(Decimal("0.01")),
        "total_loss": total_loss.quantize(Decimal("0.01")),
        "balance_error": balance_error.quantize(Decimal("0.01")),
        "balance_error_percent": balance_error_percent,
    }
