import argparse
import random
import time
import threading
from datetime import datetime, timezone

import requests

WATER_LEVEL_DESIGN_VALUES = {
    f"WL-{i:03d}": round(random.uniform(1.5, 6.0), 2) for i in range(1, 51)
}

FLOW_DESIGN_VALUES = {
    f"FL-{i:03d}": round(random.uniform(5.0, 50.0), 2) for i in range(1, 51)
}

SENSOR_CONFIGS = []
for _code, _dv in WATER_LEVEL_DESIGN_VALUES.items():
    SENSOR_CONFIGS.append(("water_level", _code, _dv))
for _code, _dv in FLOW_DESIGN_VALUES.items():
    SENSOR_CONFIGS.append(("flow", _code, _dv))

SCENARIOS = {
    "normal": {"abnormal_rate": 0.05, "surge_sensors": [], "surge_factor": 0, "outage_probability": 0, "outage_duration": 0},
    "surge": {"abnormal_rate": 0.05, "surge_sensors": ["WL-001", "WL-005", "WL-010", "WL-020", "WL-030"], "surge_factor": 0.30, "outage_probability": 0, "outage_duration": 0},
    "outage": {"abnormal_rate": 0.05, "surge_sensors": [], "surge_factor": 0, "outage_probability": 0.15, "outage_duration": 30},
    "surge_and_outage": {"abnormal_rate": 0.10, "surge_sensors": ["WL-001", "WL-005", "WL-010", "WL-020", "WL-030", "WL-040", "WL-050"], "surge_factor": 0.35, "outage_probability": 0.20, "outage_duration": 60},
    "extreme": {"abnormal_rate": 0.30, "surge_sensors": ["WL-001", "WL-005", "WL-010", "WL-015", "WL-020", "WL-025", "WL-030", "WL-035", "WL-040", "WL-045", "WL-050"], "surge_factor": 0.50, "outage_probability": 0.30, "outage_duration": 120},
}

current_scenario = "normal"
outage_active = False
outage_end_time = 0
scenario_lock = threading.Lock()


def inject_surge(value, sensor_code, scenario):
    if sensor_code in scenario["surge_sensors"] and scenario["surge_factor"] > 0:
        direction = random.choice([-1, 1])
        factor = 1 + direction * random.uniform(scenario["surge_factor"] * 0.5, scenario["surge_factor"])
        return round(value * factor, 4)
    return value


def generate_sensor_value(sensor_type, design_value, sensor_code, scenario):
    is_abnormal = random.random() < scenario["abnormal_rate"]

    if sensor_type == "water_level":
        if is_abnormal:
            spike_direction = random.choice([-1, 1])
            spike_factor = 1 + spike_direction * random.uniform(0.10, 0.25)
            value = round(design_value * spike_factor, 4)
        else:
            noise = random.uniform(-0.05, 0.05)
            value = round(design_value * (1 + noise), 4)
    else:
        if is_abnormal:
            spike_direction = random.choice([-1, 1])
            spike_factor = 1 + spike_direction * random.uniform(0.10, 0.20)
            value = round(design_value * spike_factor, 4)
        else:
            noise = random.uniform(-0.03, 0.03)
            value = round(design_value * (1 + noise), 4)

    value = inject_surge(value, sensor_code, scenario)
    return value


def build_batch(api_key, scenario):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    readings = []
    for sensor_type, code, design_value in SENSOR_CONFIGS:
        value = generate_sensor_value(sensor_type, design_value, code, scenario)
        readings.append({
            "sensor_code": code,
            "value": value,
            "recorded_at": now,
        })
    return {"api_key": api_key, "data": readings}


def print_batch_summary(batch, response_status, skipped=False):
    if skipped:
        print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] OUTAGE - batch skipped (DTU communication interrupted)")
        return
    values = [r["value"] for r in batch["data"]]
    wl_values = [r["value"] for r in batch["data"] if r["sensor_code"].startswith("WL")]
    fl_values = [r["value"] for r in batch["data"] if r["sensor_code"].startswith("FL")]
    timestamp = batch["data"][0]["recorded_at"]
    print(f"[{timestamp}] Batch sent | Status: {response_status} | Count: {len(batch['data'])}")
    print(f"  Water Level - min: {min(wl_values):.4f}  max: {max(wl_values):.4f}")
    print(f"  Flow        - min: {min(fl_values):.4f}  max: {max(fl_values):.4f}")


def scenario_input_thread():
    global current_scenario, outage_active, outage_end_time
    while True:
        try:
            cmd = input().strip().lower()
            with scenario_lock:
                if cmd in SCENARIOS:
                    current_scenario = cmd
                    print(f">>> Scenario changed to: {cmd}")
                elif cmd.startswith("outage "):
                    duration = int(cmd.split()[1])
                    outage_active = True
                    outage_end_time = time.time() + duration
                    print(f">>> Manual outage injected for {duration}s")
                elif cmd == "clear_outage":
                    outage_active = False
                    print(">>> Outage cleared")
                elif cmd == "status":
                    print(f">>> Current scenario: {current_scenario} | Outage active: {outage_active}")
                elif cmd == "help":
                    print(">>> Commands: normal|surge|outage|surge_and_outage|extreme|outage <seconds>|clear_outage|status|help")
        except EOFError:
            break
        except Exception:
            pass


def run_simulator(api_url, interval, api_key, scenario_name):
    global current_scenario, outage_active, outage_end_time

    endpoint = f"{api_url.rstrip('/')}/api/dtu/data"

    if scenario_name not in SCENARIOS:
        scenario_name = "normal"
    current_scenario = scenario_name

    print("=" * 60)
    print("  DTU Simulator - 跨流域调水工程4G DTU数据上报模拟器")
    print("=" * 60)
    print(f"  Endpoint:     {endpoint}")
    print(f"  Interval:     {interval}s")
    print(f"  Sensors:      {len(SENSOR_CONFIGS)} ({len(WATER_LEVEL_DESIGN_VALUES)} water_level, {len(FLOW_DESIGN_VALUES)} flow)")
    print(f"  Scenario:     {current_scenario}")
    print(f"  Available:    {', '.join(SCENARIOS.keys())}")
    print(f"  Interactive:  normal|surge|outage|surge_and_outage|extreme|outage <sec>|clear_outage|status")
    print("=" * 60)
    print()

    input_thread = threading.Thread(target=scenario_input_thread, daemon=True)
    input_thread.start()

    batch_count = 0
    while True:
        with scenario_lock:
            scenario = SCENARIOS[current_scenario]
            is_outage = outage_active
            if outage_active and time.time() > outage_end_time:
                outage_active = False
                is_outage = False
                print(">>> Outage ended - resuming data transmission")

        if is_outage:
            print_batch_summary(None, None, skipped=True)
            time.sleep(interval)
            continue

        batch = build_batch(api_key, scenario)
        batch_count += 1
        try:
            resp = requests.post(endpoint, json=batch, timeout=10)
            print_batch_summary(batch, resp.status_code)
            if resp.status_code == 200:
                result = resp.json()
                print(f"  Server: inserted={result.get('inserted', '?')} warnings={len(result.get('warnings', []))}")
            else:
                print(f"  Server error: {resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            print_batch_summary(batch, "FAILED")
            print(f"  Connection error: {e}")

        if scenario["outage_probability"] > 0 and random.random() < scenario["outage_probability"]:
            with scenario_lock:
                outage_active = True
                outage_end_time = time.time() + scenario["outage_duration"]
            print(f">>> Random outage triggered! DTU offline for {scenario['outage_duration']}s")

        print()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="DTU Simulator - simulates 4G DTU sensor data reporting")
    parser.add_argument("--api-url", default="http://localhost:8000", help="FastAPI backend URL")
    parser.add_argument("--interval", type=int, default=300, help="Reporting interval in seconds (default: 300)")
    parser.add_argument("--api-key", default="dtu-secret-key-2024", help="DTU API key")
    parser.add_argument("--scenario", default="normal", choices=list(SCENARIOS.keys()),
                        help="Initial scenario: normal, surge, outage, surge_and_outage, extreme")
    args = parser.parse_args()
    run_simulator(args.api_url, args.interval, args.api_key, args.scenario)


if __name__ == "__main__":
    main()
