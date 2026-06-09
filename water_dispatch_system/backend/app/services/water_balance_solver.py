import uuid
import math
from decimal import Decimal

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Canal, CanalSection, Sensor, SensorData,
    Gate, GateStatus, PumpStation, PumpStatus, DispatchCommand,
)
from app.database import async_session
from app.services.redis_service import redis_pubsub
from app.config import (
    GRAVITY, WAVE_SPEED_FACTOR, ATTENUATION_PER_KM,
    MIN_WATER_LEVEL, MAX_FLOW_CHANGE_RATE, MAX_STORAGE_CHANGE_RATIO,
    MAX_LEVEL_RATIO, LOSS_RATE,
    DISPATCH_LOW_WATER_DEMAND_FACTOR, DISPATCH_LOW_WATER_THRESHOLD,
    DISPATCH_RAMP_TIME_MINUTES, DISPATCH_RAMP_MIN_FACTOR,
    DISPATCH_PUMP_STOP_THRESHOLD, DISPATCH_LEVEL_DEVIATION_LOW,
    DISPATCH_LEVEL_DEVIATION_HIGH, DISPATCH_LEVEL_OVER_CORRECT_FACTOR,
)


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

    _gravity = Decimal(str(GRAVITY))
    _min_water_level = Decimal(str(MIN_WATER_LEVEL))
    _max_flow_change_rate = Decimal(str(MAX_FLOW_CHANGE_RATE))
    _max_storage_change_ratio = Decimal(str(MAX_STORAGE_CHANGE_RATIO))
    _max_level_ratio = Decimal(str(MAX_LEVEL_RATIO))
    _loss_rate = Decimal(str(LOSS_RATE))
    _low_water_demand_factor = Decimal(str(DISPATCH_LOW_WATER_DEMAND_FACTOR))
    _low_water_threshold = Decimal(str(DISPATCH_LOW_WATER_THRESHOLD))
    _ramp_time_minutes = Decimal(str(DISPATCH_RAMP_TIME_MINUTES))
    _ramp_min_factor = Decimal(str(DISPATCH_RAMP_MIN_FACTOR))
    _pump_stop_threshold = Decimal(str(DISPATCH_PUMP_STOP_THRESHOLD))
    _level_deviation_low = Decimal(str(DISPATCH_LEVEL_DEVIATION_LOW))
    _level_deviation_high = Decimal(str(DISPATCH_LEVEL_DEVIATION_HIGH))
    _level_over_correct_factor = Decimal(str(DISPATCH_LEVEL_OVER_CORRECT_FACTOR))

    section_states = []
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

        section_length_km = float(section.end_km - section.start_km)
        design_depth = float(section.design_water_level) if section.design_water_level else 5.0
        wave_speed = WAVE_SPEED_FACTOR * math.sqrt(GRAVITY * design_depth)
        propagation_time_min = (section_length_km * 1000.0 / wave_speed / 60.0) if wave_speed > 0 else 0.0
        attenuation = 1.0 - ATTENUATION_PER_KM * section_length_km
        attenuation = max(attenuation, 0.5)

        section_states.append({
            "section": section,
            "pumps": pumps,
            "gates": gates,
            "current_water_level": current_water_level,
            "design_water_level": section.design_water_level,
            "section_inflow": section_inflow,
            "section_outflow": section_outflow,
            "running_pumps": running_pumps,
            "propagation_time_min": propagation_time_min,
            "attenuation": Decimal(str(round(attenuation, 4))),
            "length_km": section_length_km,
            "storage_capacity": section.storage_capacity,
        })

    for idx, state in enumerate(section_states):
        section = state["section"]
        pumps = state["pumps"]
        gates = state["gates"]
        current_water_level = state["current_water_level"]
        design_water_level = state["design_water_level"]
        section_inflow = state["section_inflow"]
        section_outflow = state["section_outflow"]
        running_pumps = state["running_pumps"]
        attenuation = state["attenuation"]
        propagation_time_min = state["propagation_time_min"]
        storage_capacity = state["storage_capacity"]

        delayed_inflow = section_inflow
        if idx > 0:
            upstream = section_states[idx - 1]
            flow_change = upstream["section_inflow"] - upstream["section_outflow"]
            if flow_change != Decimal("0"):
                delay_factor = Decimal("1.0") / (Decimal("1.0") + Decimal(str(round(propagation_time_min / float(_ramp_time_minutes), 2))))
                delayed_inflow = section_inflow + flow_change * attenuation * delay_factor

        flow_change = delayed_inflow - section_outflow
        max_change = delayed_inflow * _max_flow_change_rate if delayed_inflow > Decimal("0") else Decimal("10")
        flow_change = max(-abs(max_change), min(abs(max_change), flow_change))

        if design_water_level and design_water_level > Decimal("0"):
            level_ratio = current_water_level / design_water_level
        else:
            level_ratio = Decimal("1.0")
        current_storage = level_ratio * storage_capacity

        ds = flow_change
        max_ds = current_storage * _max_storage_change_ratio
        ds = max(-abs(max_ds), min(abs(max_ds), ds))
        new_storage = current_storage + ds

        if storage_capacity > Decimal("0"):
            new_level_ratio = new_storage / storage_capacity
            new_level_ratio = max(Decimal("0"), min(_max_level_ratio, new_level_ratio))
        else:
            new_level_ratio = level_ratio

        clamped_level = new_level_ratio * design_water_level
        if clamped_level < _min_water_level:
            clamped_level = _min_water_level
            new_storage = (clamped_level / design_water_level) * storage_capacity if design_water_level > Decimal("0") else Decimal("0")
            ds = new_storage - current_storage

        total_inflow += delayed_inflow
        total_outflow += section_outflow
        total_storage_change += ds

        demand_share = demand_per_section * (section.design_flow / canal.design_flow) if canal.design_flow > Decimal("0") else demand_per_section
        target_level_ratio = Decimal("1.0")
        if design_water_level > Decimal("0"):
            level_deviation = current_water_level / design_water_level
            if level_deviation < _level_deviation_low:
                target_level_ratio = Decimal("1.0")
            elif level_deviation > _level_deviation_high:
                target_level_ratio = Decimal("0.9")
            else:
                target_level_ratio = Decimal("1.0") - (level_deviation - Decimal("1.0")) * _level_over_correct_factor

        required_flow = demand_share * target_level_ratio
        if clamped_level <= _low_water_threshold:
            required_flow = required_flow * _low_water_demand_factor
        if idx > 0 and propagation_time_min > float(_ramp_time_minutes):
            ramp_factor = _ramp_time_minutes / Decimal(str(round(propagation_time_min, 1)))
            ramp_factor = max(_ramp_min_factor, min(Decimal("1.0"), ramp_factor))
            required_flow = section_outflow + (required_flow - section_outflow) * ramp_factor

        required_flow = required_flow.quantize(Decimal("0.01"))

        for gate in gates:
            opening = Decimal("0")
            if gate.design_flow and gate.design_flow > Decimal("0"):
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
            if single_pump_flow == Decimal("0"):
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
            elif needed_flow < current_capacity * _pump_stop_threshold:
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

    total_loss = total_inflow * _loss_rate
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

    plan = {
        "plan_id": plan_id,
        "canal_id": canal_id,
        "commands": commands,
        "water_balance": water_balance,
    }

    await redis_pubsub.publish("dispatch_command", {
        "plan_id": plan_id,
        "commands": commands,
        "water_balance": water_balance,
    })

    return plan


async def calculate_water_balance(
    canal_id: int, db: AsyncSession
) -> dict:
    canal_stmt = select(Canal).where(Canal.id == canal_id)
    canal_result = await db.execute(canal_stmt)
    canal = canal_result.scalar_one_or_none()
    if not canal:
        return {}

    _loss_rate = Decimal(str(LOSS_RATE))

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

    total_loss = total_inflow * _loss_rate
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
