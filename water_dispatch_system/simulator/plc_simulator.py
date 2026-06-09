import argparse
import json
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

COMMAND_TOPIC_PREFIX = "dispatch/command"
RESPONSE_TOPIC_PREFIX = "dispatch/response"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        topic = f"{COMMAND_TOPIC_PREFIX}/#"
        client.subscribe(topic, qos=1)
        print(f"Connected to broker | Subscribed to {topic}")
    else:
        print(f"Connection failed with code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"Invalid message on {msg.topic}")
        return

    command_id = payload.get("command_id")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    command_type = payload.get("command_type")
    command_value = payload.get("command_value")

    print(f"Command received: command_id={command_id} target_type={target_type} target_id={target_id} command_type={command_type} command_value={command_value}")

    delay = random.uniform(1.0, 3.0)
    time.sleep(delay)

    if target_type == "gate":
        print(f"Gate {target_id} opening set to {command_value}%")
    elif target_type == "pump":
        print(f"Pump station {target_id} running count set to {command_value}")

    variance = random.uniform(-0.02, 0.02)
    if command_value is not None:
        actual_value = round(command_value * (1 + variance), 2)
    else:
        actual_value = None

    response = {
        "command_id": command_id,
        "status": "executed",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actual_value": actual_value,
    }

    response_topic = f"{RESPONSE_TOPIC_PREFIX}/{target_type}/{target_id}"
    client.publish(response_topic, json.dumps(response), qos=1)
    print(f"Ack published to {response_topic} | status=executed actual_value={actual_value}")
    print()


def on_disconnect(client, userdata, rc):
    print(f"Disconnected from broker (rc={rc})")


def run_simulator(broker, port):
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"PLC Simulator started")
    print(f"  Broker: {broker}:{port}")
    print()

    client.connect(broker, port, 60)
    client.loop_forever()


def main():
    parser = argparse.ArgumentParser(description="PLC Simulator - simulates PLC devices receiving dispatch commands via MQTT")
    parser.add_argument("--broker", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    args = parser.parse_args()
    run_simulator(args.broker, args.port)


if __name__ == "__main__":
    main()
