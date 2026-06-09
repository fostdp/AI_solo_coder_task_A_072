import json
import paho.mqtt.client as mqtt
from app.config import MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, DISPATCH_TOPIC_PREFIX, PLC_RESPONSE_TOPIC_PREFIX


class MQTTService:
    def __init__(self):
        self.broker = MQTT_BROKER
        self.port = MQTT_PORT
        self.username = MQTT_USERNAME
        self.password = MQTT_PASSWORD
        self.client = mqtt.Client()
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, payload: dict):
        self.client.publish(topic, json.dumps(payload), qos=1)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"MQTT connected to {self.broker}:{self.port}")
        else:
            print(f"MQTT connection failed with code {rc}")
        client.subscribe(PLC_RESPONSE_TOPIC_PREFIX + "/#")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if msg.topic.startswith(PLC_RESPONSE_TOPIC_PREFIX):
            pass

    def _on_disconnect(self, client, userdata, rc):
        print(f"MQTT disconnected (rc={rc})")


mqtt_client = MQTTService()
