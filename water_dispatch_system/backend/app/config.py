import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/water_dispatch")
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

DTU_API_KEY = os.getenv("DTU_API_KEY", "dtu-secret-key-2024")

ALARM_LEVEL1_DURATION_MINUTES = 10
ALARM_LEVEL2_FLOW_DEVIATION_PERCENT = 20

SENSOR_REPORT_INTERVAL_SECONDS = 300

DISPATCH_TOPIC_PREFIX = "dispatch/command"
PLC_RESPONSE_TOPIC_PREFIX = "dispatch/response"
