import json
import time
import threading
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
        self._connected = False
        self._lock = threading.Lock()
        self.pending_queue = []
        self.acked_commands = {}
        self.MAX_QUEUE_SIZE = 1000
        self.ACK_TIMEOUT_SECONDS = 300

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, payload: dict):
        command_id = payload.get("command_id") or payload.get("plan_id", "") + "-" + str(payload.get("target_id", ""))
        message = {
            "topic": topic,
            "payload": payload,
            "command_id": command_id,
            "queued_at": time.time(),
            "attempts": 0,
        }

        with self._lock:
            if len(self.pending_queue) >= self.MAX_QUEUE_SIZE:
                self.pending_queue = self.pending_queue[self.MAX_QUEUE_SIZE // 2:]
            self.pending_queue.append(message)

        self._try_send(message)

    def _try_send(self, message):
        if not self._connected:
            return
        try:
            result = self.client.publish(message["topic"], json.dumps(message["payload"]), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                with self._lock:
                    if message in self.pending_queue:
                        self.pending_queue.remove(message)
                    message["attempts"] += 1
                    self.acked_commands[message["command_id"]] = {
                        "message": message,
                        "sent_at": time.time(),
                        "acked": False,
                    }
        except Exception:
            pass

    def _flush_pending_queue(self):
        with self._lock:
            queue_copy = list(self.pending_queue)
        for message in queue_copy:
            self._try_send(message)

    def _cleanup_acked_commands(self):
        now = time.time()
        with self._lock:
            expired = []
            for cid, entry in self.acked_commands.items():
                if entry["acked"]:
                    expired.append(cid)
                elif now - entry["sent_at"] > self.ACK_TIMEOUT_SECONDS:
                    expired.append(cid)
                    self.pending_queue.append(entry["message"])
            for cid in expired:
                del self.acked_commands[cid]

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            print(f"MQTT connected to {self.broker}:{self.port}")
            client.subscribe(PLC_RESPONSE_TOPIC_PREFIX + "/#", qos=1)
            self._flush_pending_queue()
        else:
            self._connected = False
            print(f"MQTT connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if msg.topic.startswith(PLC_RESPONSE_TOPIC_PREFIX):
            command_id = data.get("command_id")
            if command_id:
                with self._lock:
                    if command_id in self.acked_commands:
                        self.acked_commands[command_id]["acked"] = True
            self._cleanup_acked_commands()

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        print(f"MQTT disconnected (rc={rc}), {len(self.pending_queue)} commands queued")


mqtt_client = MQTTService()
