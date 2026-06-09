import argparse
import json
import random
import time
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

COMMAND_TOPIC_PREFIX = "dispatch/command"
RESPONSE_TOPIC_PREFIX = "dispatch/response"

gate_states = {}
pump_states = {}
state_lock = threading.Lock()


def get_gate_state(gate_id):
    with state_lock:
        if gate_id not in gate_states:
            gate_states[gate_id] = {"opening": 100.0, "flow": 0.0, "status": "normal"}
        return gate_states[gate_id].copy()


def set_gate_state(gate_id, key, value):
    with state_lock:
        if gate_id not in gate_states:
            gate_states[gate_id] = {"opening": 100.0, "flow": 0.0, "status": "normal"}
        gate_states[gate_id][key] = value


def get_pump_state(station_id):
    with state_lock:
        if station_id not in pump_states:
            pump_states[station_id] = {"running_count": 0, "total_power": 0.0, "total_flow": 0.0, "status": "stopped"}
        return pump_states[station_id].copy()


def set_pump_state(station_id, key, value):
    with state_lock:
        if station_id not in pump_states:
            pump_states[station_id] = {"running_count": 0, "total_power": 0.0, "total_flow": 0.0, "status": "stopped"}
        pump_states[station_id][key] = value


def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        topic = f"{COMMAND_TOPIC_PREFIX}/#"
        client.subscribe(topic, qos=1)
        print(f"Connected to broker | Subscribed to {topic} (QoS 1)")
    else:
        print(f"Connection failed with code {rc}")


def handle_gate_command(client, target_id, command_type, command_value, command_id):
    gate_id = str(target_id)
    current = get_gate_state(gate_id)

    if command_type == "set_opening":
        opening = max(0.0, min(100.0, float(command_value)))
        variance = random.uniform(-0.02, 0.02)
        actual_opening = round(opening * (1 + variance), 2)
        actual_opening = max(0.0, min(100.0, actual_opening))

        set_gate_state(gate_id, "opening", actual_opening)
        design_flow = 100.0
        actual_flow = round(design_flow * (actual_opening / 100.0) * (1 + random.uniform(-0.03, 0.03)), 2)
        set_gate_state(gate_id, "flow", actual_flow)
        set_gate_state(gate_id, "status", "normal" if 10 <= actual_opening <= 95 else "warning")

        print(f"  Gate {gate_id}: opening {current.get('opening', '?')}% -> {actual_opening}% | flow={actual_flow} m3/s")

        response = {
            "command_id": command_id,
            "target_type": "gate",
            "target_id": target_id,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual_value": actual_opening,
            "gate_opening": actual_opening,
            "gate_flow": actual_flow,
        }
    else:
        response = {
            "command_id": command_id,
            "target_type": "gate",
            "target_id": target_id,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual_value": command_value,
        }

    response_topic = f"{RESPONSE_TOPIC_PREFIX}/gate/{gate_id}"
    client.publish(response_topic, json.dumps(response), qos=1)
    print(f"  ACK published to {response_topic}")


def handle_pump_command(client, target_id, command_type, command_value, command_id):
    station_id = str(target_id)
    current = get_pump_state(station_id)
    pump_count = 4
    single_pump_power = 500.0
    single_pump_flow = 25.0

    if command_type == "start_pumps":
        start_count = int(command_value)
        new_running = min(current["running_count"] + start_count, pump_count)
        actual_started = new_running - current["running_count"]
        set_pump_state(station_id, "running_count", new_running)
        set_pump_state(station_id, "total_power", round(new_running * single_pump_power * (1 + random.uniform(-0.02, 0.02)), 2))
        set_pump_state(station_id, "total_flow", round(new_running * single_pump_flow * (1 + random.uniform(-0.03, 0.03)), 2))
        set_pump_state(station_id, "status", "running" if new_running > 0 else "stopped")

        print(f"  Pump {station_id}: started {actual_started} pumps | running={new_running}/{pump_count}")

        response = {
            "command_id": command_id,
            "target_type": "pump",
            "target_id": target_id,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual_value": actual_started,
            "running_count": new_running,
            "total_power": get_pump_state(station_id)["total_power"],
            "total_flow": get_pump_state(station_id)["total_flow"],
        }

    elif command_type == "stop_pumps":
        stop_count = int(command_value)
        new_running = max(0, current["running_count"] - stop_count)
        actual_stopped = current["running_count"] - new_running
        set_pump_state(station_id, "running_count", new_running)
        set_pump_state(station_id, "total_power", round(new_running * single_pump_power * (1 + random.uniform(-0.02, 0.02)), 2))
        set_pump_state(station_id, "total_flow", round(new_running * single_pump_flow * (1 + random.uniform(-0.03, 0.03)), 2))
        set_pump_state(station_id, "status", "running" if new_running > 0 else "stopped")

        print(f"  Pump {station_id}: stopped {actual_stopped} pumps | running={new_running}/{pump_count}")

        response = {
            "command_id": command_id,
            "target_type": "pump",
            "target_id": target_id,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual_value": actual_stopped,
            "running_count": new_running,
            "total_power": get_pump_state(station_id)["total_power"],
            "total_flow": get_pump_state(station_id)["total_flow"],
        }

    else:
        response = {
            "command_id": command_id,
            "target_type": "pump",
            "target_id": target_id,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actual_value": command_value,
        }

    response_topic = f"{RESPONSE_TOPIC_PREFIX}/pump/{station_id}"
    client.publish(response_topic, json.dumps(response), qos=1)
    print(f"  ACK published to {response_topic}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"Invalid message on {msg.topic}")
        return

    command_id = payload.get("command_id", "unknown")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")
    command_type = payload.get("command_type")
    command_value = payload.get("command_value")

    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] CMD: id={command_id} type={target_type}/{command_type} target={target_id} value={command_value}")

    delay = random.uniform(0.5, 2.5)
    time.sleep(delay)

    if target_type == "gate":
        handle_gate_command(client, target_id, command_type, command_value, command_id)
    elif target_type == "pump":
        handle_pump_command(client, target_id, command_type, command_value, command_id)
    else:
        print(f"  Unknown target type: {target_type}")

    print()


def on_disconnect(client, userdata, rc, props=None):
    print(f"Disconnected from broker (rc={rc})")


def status_report():
    while True:
        time.sleep(60)
        with state_lock:
            gate_count = len(gate_states)
            pump_count = len(pump_states)
            total_running = sum(s["running_count"] for s in pump_states.values())
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] Status: {gate_count} gates tracked, {pump_count} pump stations tracked, {total_running} pumps running")


def run_simulator(broker, port):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="plc-simulator-001", clean_session=False)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print("=" * 60)
    print("  PLC Simulator - 跨流域调水工程现地PLC模拟器")
    print("=" * 60)
    print(f"  Broker:       {broker}:{port}")
    print(f"  Client ID:    plc-simulator-001")
    print(f"  Clean Session: False (persistent)")
    print(f"  Subscribe:    {COMMAND_TOPIC_PREFIX}/# (QoS 1)")
    print("=" * 60)
    print()

    report_thread = threading.Thread(target=status_report, daemon=True)
    report_thread.start()

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
