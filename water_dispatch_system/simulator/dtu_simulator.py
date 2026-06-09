import argparse
import random
import time
from datetime import datetime, timezone

import requests


WATER_LEVEL_DESIGN_VALUES = {
    f"WL-{i:03d}": round(random.uniform(1.5, 6.0), 2) for i in range(1, 51)
}

FLOW_DESIGN_VALUES = {
    f"FL-{i:03d}": round(random.uniform(5.0, 50.0), 2) for i in range(1, 51)
}

SENSOR_CONFIGS = []
for code, dv in WATER_LEVEL_DESIGN_VALUES.items():
    SENSOR_CONFIGS.append(("water_level", code, dv))
for code, dv in FLOW_DESIGN_VALUES.items():
    SENSOR_CONFIGS.append(("flow", code, dv))


def generate_sensor_value(sensor_type, design_value):
    is_abnormal = random.random() < 0.05

    if sensor_type == "water_level":
        if is_abnormal:
            spike_direction = random.choice([-1, 1])
            spike_factor = 1 + spike_direction * random.uniform(0.10, 0.25)
            return round(design_value * spike_factor, 4)
        noise = random.uniform(-0.05, 0.05)
        return round(design_value * (1 + noise), 4)

    if is_abnormal:
        spike_direction = random.choice([-1, 1])
        spike_factor = 1 + spike_direction * random.uniform(0.10, 0.20)
        return round(design_value * spike_factor, 4)
    noise = random.uniform(-0.03, 0.03)
    return round(design_value * (1 + noise), 4)


def build_batch(api_key):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    readings = []
    for sensor_type, code, design_value in SENSOR_CONFIGS:
        value = generate_sensor_value(sensor_type, design_value)
        readings.append({
            "sensor_code": code,
            "value": value,
            "recorded_at": now,
        })
    return {"api_key": api_key, "data": readings}


def print_batch_summary(batch, response_status):
    values = [r["value"] for r in batch["data"]]
    wl_values = [r["value"] for r in batch["data"] if r["sensor_code"].startswith("WL")]
    fl_values = [r["value"] for r in batch["data"] if r["sensor_code"].startswith("FL")]
    timestamp = batch["data"][0]["recorded_at"]
    print(f"[{timestamp}] Batch sent | Status: {response_status} | Count: {len(batch['data'])}")
    print(f"  Water Level - min: {min(wl_values):.4f}  max: {max(wl_values):.4f}")
    print(f"  Flow        - min: {min(fl_values):.4f}  max: {max(fl_values):.4f}")


def run_simulator(api_url, interval, api_key):
    endpoint = f"{api_url.rstrip('/')}/api/dtu/data"
    print(f"DTU Simulator started")
    print(f"  Endpoint: {endpoint}")
    print(f"  Interval: {interval}s")
    print(f"  Sensors: {len(SENSOR_CONFIGS)} ({len(WATER_LEVEL_DESIGN_VALUES)} water_level, {len(FLOW_DESIGN_VALUES)} flow)")
    print()

    while True:
        batch = build_batch(api_key)
        try:
            resp = requests.post(endpoint, json=batch, timeout=10)
            print_batch_summary(batch, resp.status_code)
            if resp.status_code == 200:
                result = resp.json()
                print(f"  Server response: inserted={result.get('inserted', '?')}")
            else:
                print(f"  Server error: {resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            print_batch_summary(batch, "FAILED")
            print(f"  Connection error: {e}")

        print()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="DTU Simulator - simulates 4G DTU sensor data reporting")
    parser.add_argument("--api-url", default="http://localhost:8000", help="FastAPI backend URL")
    parser.add_argument("--interval", type=int, default=300, help="Reporting interval in seconds")
    parser.add_argument("--api-key", default="dtu-secret-key-2024", help="DTU API key")
    args = parser.parse_args()
    run_simulator(args.api_url, args.interval, args.api_key)


if __name__ == "__main__":
    main()
