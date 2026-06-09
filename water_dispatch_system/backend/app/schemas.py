from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class CanalOut(BaseModel):
    id: int
    name: str
    code: str
    length_km: Decimal
    design_flow: Decimal
    geom_geojson: Optional[dict] = None
    class Config:
        from_attributes = True


class CanalSectionOut(BaseModel):
    id: int
    canal_id: int
    name: str
    code: str
    start_km: Decimal
    end_km: Decimal
    design_water_level: Decimal
    design_flow: Decimal
    storage_capacity: Decimal
    geom_geojson: Optional[dict] = None
    class Config:
        from_attributes = True


class PumpStationOut(BaseModel):
    id: int
    canal_id: int
    section_id: int
    name: str
    code: str
    pump_count: int
    single_pump_power: Decimal
    design_flow: Decimal
    head: Decimal
    lng: Optional[float] = None
    lat: Optional[float] = None
    latest_status: Optional["PumpStatusOut"] = None
    class Config:
        from_attributes = True


class GateOut(BaseModel):
    id: int
    canal_id: int
    section_id: int
    name: str
    code: str
    gate_type: str
    max_opening: Decimal
    design_flow: Decimal
    lng: Optional[float] = None
    lat: Optional[float] = None
    latest_status: Optional["GateStatusOut"] = None
    class Config:
        from_attributes = True


class SensorOut(BaseModel):
    id: int
    canal_id: int
    section_id: int
    name: str
    code: str
    sensor_type: str
    design_value: Decimal
    warning_upper: Decimal
    warning_lower: Decimal
    danger_upper: Decimal
    danger_lower: Decimal
    lng: Optional[float] = None
    lat: Optional[float] = None
    latest_value: Optional[Decimal] = None
    deviation_percent: Optional[float] = None
    status_color: Optional[str] = None
    class Config:
        from_attributes = True


class SensorDataOut(BaseModel):
    id: int
    sensor_id: int
    value: Decimal
    recorded_at: datetime
    class Config:
        from_attributes = True


class GateStatusOut(BaseModel):
    id: int
    gate_id: int
    opening: Decimal
    flow: Optional[Decimal]
    recorded_at: datetime
    class Config:
        from_attributes = True


class PumpStatusOut(BaseModel):
    id: int
    pump_station_id: int
    running_count: int
    total_power: Decimal
    total_flow: Decimal
    recorded_at: datetime
    class Config:
        from_attributes = True


class AlarmOut(BaseModel):
    id: int
    alarm_type: str
    level: int
    source_type: str
    source_id: int
    source_name: Optional[str]
    message: str
    value: Optional[Decimal]
    threshold: Optional[Decimal]
    duration_minutes: Optional[int]
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    class Config:
        from_attributes = True


class DispatchCommandOut(BaseModel):
    id: int
    plan_id: Optional[str]
    target_type: str
    target_id: int
    target_name: Optional[str]
    command_type: str
    command_value: Optional[Decimal]
    mqtt_topic: Optional[str]
    status: str
    created_at: datetime
    sent_at: Optional[datetime]
    acked_at: Optional[datetime]
    class Config:
        from_attributes = True


class DTUDataIn(BaseModel):
    sensor_code: str
    value: Decimal
    recorded_at: datetime


class DTUBatchIn(BaseModel):
    api_key: str
    data: List[DTUDataIn]


class DispatchRequest(BaseModel):
    canal_id: int
    downstream_demand: Decimal
    priority: Optional[str] = "normal"


class DispatchPlanOut(BaseModel):
    plan_id: str
    canal_id: int
    commands: List[DispatchCommandOut]
    water_balance: "WaterBalanceOut"
    class Config:
        from_attributes = True


class WaterBalanceOut(BaseModel):
    canal_id: int
    canal_name: str
    total_inflow: Decimal
    total_outflow: Decimal
    total_storage_change: Decimal
    total_loss: Decimal
    balance_error: Decimal
    balance_error_percent: float
    class Config:
        from_attributes = True


class KPIWaterBalanceOut(BaseModel):
    canals: List[WaterBalanceOut]
    total_inflow: Decimal
    total_outflow: Decimal
    total_storage_change: Decimal


class KPIWaterLevelOut(BaseModel):
    section_id: int
    section_name: str
    canal_name: str
    current_level: Optional[Decimal]
    design_level: Decimal
    deviation_percent: Optional[float]
    status_color: Optional[str]


class KPIPumpPowerOut(BaseModel):
    station_id: int
    station_name: str
    running_count: int
    total_pump_count: int
    total_power: Decimal
    max_power: Decimal
    load_percent: float


class AlarmAckRequest(BaseModel):
    alarm_ids: List[int]


class SensorHistoryOut(BaseModel):
    sensor: SensorOut
    data: List[SensorDataOut]
    dispatch_history: List[DispatchCommandOut]


PumpStationOut.model_rebuild()
GateOut.model_rebuild()
DispatchPlanOut.model_rebuild()
