import os
from pathlib import Path
import yaml


def _load_yaml_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_yaml = _load_yaml_config()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/water_dispatch")

_wb = _yaml.get("water_balance", {})
GRAVITY = float(os.getenv("WB_GRAVITY", _wb.get("gravity", 9.81)))
WAVE_SPEED_FACTOR = float(os.getenv("WB_WAVE_SPEED_FACTOR", _wb.get("wave_speed_factor", 0.7)))
ATTENUATION_PER_KM = float(os.getenv("WB_ATTENUATION_PER_KM", _wb.get("attenuation_per_km", 0.003)))
MIN_WATER_LEVEL = float(os.getenv("WB_MIN_WATER_LEVEL", _wb.get("min_water_level", 0.1)))
MAX_FLOW_CHANGE_RATE = float(os.getenv("WB_MAX_FLOW_CHANGE_RATE", _wb.get("max_flow_change_rate", 0.15)))
MAX_STORAGE_CHANGE_RATIO = float(os.getenv("WB_MAX_STORAGE_CHANGE_RATIO", _wb.get("max_storage_change_ratio", 0.3)))
MAX_LEVEL_RATIO = float(os.getenv("WB_MAX_LEVEL_RATIO", _wb.get("max_level_ratio", 1.5)))
LOSS_RATE = float(os.getenv("WB_LOSS_RATE", _wb.get("loss_rate", 0.02)))

_al = _yaml.get("alarm", {})
ALARM_LEVEL1_DURATION_MINUTES = int(os.getenv("ALARM_L1_DURATION", _al.get("level1_duration_minutes", 10)))
ALARM_LEVEL2_FLOW_DEVIATION_PERCENT = int(os.getenv("ALARM_L2_DEVIATION", _al.get("level2_flow_deviation_percent", 20)))
ALARM_CHECK_INTERVAL_SECONDS = int(os.getenv("ALARM_CHECK_INTERVAL", _al.get("check_interval_seconds", 5)))
ALARM_HISTORY_WINDOW_MINUTES = int(os.getenv("ALARM_HISTORY_WINDOW", _al.get("history_window_minutes", 15)))

_dp = _yaml.get("dispatch", {})
DISPATCH_LOW_WATER_DEMAND_FACTOR = float(_dp.get("low_water_demand_factor", 0.5))
DISPATCH_LOW_WATER_THRESHOLD = float(_dp.get("low_water_threshold", 0.1))
DISPATCH_RAMP_TIME_MINUTES = float(_dp.get("ramp_time_minutes", 5))
DISPATCH_RAMP_MIN_FACTOR = float(_dp.get("ramp_min_factor", 0.3))
DISPATCH_PUMP_STOP_THRESHOLD = float(_dp.get("pump_stop_threshold", 0.8))
DISPATCH_LEVEL_DEVIATION_LOW = float(_dp.get("level_deviation_low", 0.85))
DISPATCH_LEVEL_DEVIATION_HIGH = float(_dp.get("level_deviation_high", 1.15))
DISPATCH_LEVEL_OVER_CORRECT_FACTOR = float(_dp.get("level_over_correct_factor", 0.5))

_mq = _yaml.get("mqtt", {})
MQTT_BROKER = os.getenv("MQTT_BROKER", _mq.get("broker", "localhost"))
MQTT_PORT = int(os.getenv("MQTT_PORT", _mq.get("port", 1883)))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", _mq.get("username", ""))
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", _mq.get("password", ""))
DISPATCH_TOPIC_PREFIX = _mq.get("dispatch_topic_prefix", "dispatch/command")
PLC_RESPONSE_TOPIC_PREFIX = _mq.get("plc_response_topic_prefix", "dispatch/response")
MQTT_COMMAND_QUEUE_MAX_SIZE = int(_mq.get("command_queue_max_size", 1000))
MQTT_ACK_TIMEOUT_SECONDS = int(_mq.get("ack_timeout_seconds", 300))

_rd = _yaml.get("redis", {})
REDIS_URL = os.getenv("REDIS_URL", _rd.get("url", "redis://localhost:6379/0"))
REDIS_CHANNELS = _rd.get("channels", {
    "sensor_data": "channel:sensor_data",
    "alarm_event": "channel:alarm_event",
    "dispatch_command": "channel:dispatch_command",
    "dispatch_feedback": "channel:dispatch_feedback",
})

_dtu = _yaml.get("dtu", {})
DTU_API_KEY = os.getenv("DTU_API_KEY", _dtu.get("api_key", "dtu-secret-key-2024"))
SENSOR_REPORT_INTERVAL_SECONDS = int(_dtu.get("sensor_report_interval_seconds", 300))
