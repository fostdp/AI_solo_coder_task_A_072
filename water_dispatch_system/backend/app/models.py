from sqlalchemy import Column, Integer, String, Numeric, DateTime, BigInteger, Text, ForeignKey
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from app.database import Base


class Canal(Base):
    __tablename__ = "canals"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False, unique=True)
    length_km = Column(Numeric(10, 2), nullable=False)
    design_flow = Column(Numeric(10, 2), nullable=False)
    geom = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class CanalSection(Base):
    __tablename__ = "canal_sections"
    id = Column(Integer, primary_key=True)
    canal_id = Column(Integer, ForeignKey("canals.id"))
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False)
    start_km = Column(Numeric(10, 2), nullable=False)
    end_km = Column(Numeric(10, 2), nullable=False)
    design_water_level = Column(Numeric(8, 2), nullable=False)
    design_flow = Column(Numeric(10, 2), nullable=False)
    storage_capacity = Column(Numeric(12, 2), nullable=False)
    geom = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PumpStation(Base):
    __tablename__ = "pump_stations"
    id = Column(Integer, primary_key=True)
    canal_id = Column(Integer, ForeignKey("canals.id"))
    section_id = Column(Integer, ForeignKey("canal_sections.id"))
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False)
    pump_count = Column(Integer, nullable=False, default=4)
    single_pump_power = Column(Numeric(8, 2), nullable=False)
    design_flow = Column(Numeric(10, 2), nullable=False)
    head = Column(Numeric(8, 2), nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Gate(Base):
    __tablename__ = "gates"
    id = Column(Integer, primary_key=True)
    canal_id = Column(Integer, ForeignKey("canals.id"))
    section_id = Column(Integer, ForeignKey("canal_sections.id"))
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False)
    gate_type = Column(String(20), nullable=False, default="regulating")
    max_opening = Column(Numeric(5, 2), nullable=False, default=100.0)
    design_flow = Column(Numeric(10, 2), nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Sensor(Base):
    __tablename__ = "sensors"
    id = Column(Integer, primary_key=True)
    canal_id = Column(Integer, ForeignKey("canals.id"))
    section_id = Column(Integer, ForeignKey("canal_sections.id"))
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=False)
    sensor_type = Column(String(20), nullable=False)
    design_value = Column(Numeric(10, 2), nullable=False)
    warning_upper = Column(Numeric(10, 2), nullable=False)
    warning_lower = Column(Numeric(10, 2), nullable=False)
    danger_upper = Column(Numeric(10, 2), nullable=False)
    danger_lower = Column(Numeric(10, 2), nullable=False)
    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SensorData(Base):
    __tablename__ = "sensor_data"
    id = Column(BigInteger, primary_key=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"))
    value = Column(Numeric(10, 4), nullable=False)
    recorded_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, server_default=func.now())


class GateStatus(Base):
    __tablename__ = "gate_status"
    id = Column(BigInteger, primary_key=True)
    gate_id = Column(Integer, ForeignKey("gates.id"))
    opening = Column(Numeric(5, 2), nullable=False)
    flow = Column(Numeric(10, 2))
    recorded_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, server_default=func.now())


class PumpStatus(Base):
    __tablename__ = "pump_status"
    id = Column(BigInteger, primary_key=True)
    pump_station_id = Column(Integer, ForeignKey("pump_stations.id"))
    running_count = Column(Integer, nullable=False, default=0)
    total_power = Column(Numeric(10, 2), nullable=False, default=0)
    total_flow = Column(Numeric(10, 2), nullable=False, default=0)
    recorded_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, server_default=func.now())


class Alarm(Base):
    __tablename__ = "alarms"
    id = Column(BigInteger, primary_key=True)
    alarm_type = Column(String(20), nullable=False)
    level = Column(Integer, nullable=False)
    source_type = Column(String(20), nullable=False)
    source_id = Column(Integer, nullable=False)
    source_name = Column(String(100))
    message = Column(Text, nullable=False)
    value = Column(Numeric(10, 4))
    threshold = Column(Numeric(10, 4))
    duration_minutes = Column(Integer)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, server_default=func.now())
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)


class DispatchCommand(Base):
    __tablename__ = "dispatch_commands"
    id = Column(BigInteger, primary_key=True)
    plan_id = Column(String(50))
    target_type = Column(String(20), nullable=False)
    target_id = Column(Integer, nullable=False)
    target_name = Column(String(100))
    command_type = Column(String(50), nullable=False)
    command_value = Column(Numeric(10, 2))
    mqtt_topic = Column(String(200))
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    sent_at = Column(DateTime)
    acked_at = Column(DateTime)
