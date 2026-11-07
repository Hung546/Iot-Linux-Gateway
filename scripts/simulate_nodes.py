#!/usr/bin/env python3
"""
Simulated ESP32 Nodes for Do An 1 (N06).
Simulates Node 1 (esp32_01: SHT3x + PMS5003) and Node 2 (esp32_02: SHT3x + SCD4x CO2).
Sends telemetry to the Linux Gateway via HTTP REST API or MQTT.
Allows testing without requiring physical ESP32 hardware.
"""

import sys
import time
import random
import urllib.request
import urllib.error
import json
import argparse
from datetime import datetime, timezone


class ESP32NodeSimulator:
    def __init__(self, node_id, sensor_types, gateway_url="http://127.0.0.1:8080/api/v1/telemetry", start_seq=1):
        self.node_id = node_id
        self.sensor_types = sensor_types  # e.g. ["sht3x", "pms5003"] or ["sht3x", "scd4x"]
        self.gateway_url = gateway_url
        self.seq_number = start_seq

        # State for continuous realistic sensor simulation
        self.temp = random.uniform(27.0, 29.5)
        self.hum = random.uniform(60.0, 70.0)
        self.pm25 = random.uniform(15.0, 25.0)
        self.co2 = random.uniform(500.0, 650.0)

    def _generate_telemetry(self, sensor_error=False):
        """Generates payload adhering strictly to M0/M1 JSON schema."""
        # Random drift
        self.temp = round(max(20.0, min(38.0, self.temp + random.uniform(-0.4, 0.4))), 1)
        self.hum = round(max(35.0, min(90.0, self.hum + random.uniform(-1.0, 1.0))), 1)
        self.pm25 = round(max(5.0, min(120.0, self.pm25 + random.uniform(-1.5, 1.5))), 1)
        self.co2 = round(max(400.0, min(1500.0, self.co2 + random.uniform(-15.0, 15.0))), 0)

        sensors = {}
        if "sht3x" in self.sensor_types:
            sensors["temperature_c"] = None if sensor_error else self.temp
            sensors["humidity_pct"] = self.hum

        if "pms5003" in self.sensor_types:
            sensors["pm25_ug_m3"] = self.pm25

        if "scd4x" in self.sensor_types:
            sensors["co2_ppm"] = self.co2

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        msg_id = f"{self.node_id}-{self.seq_number:06d}"
        self.seq_number += 1

        payload = {
            "schema_version": 1,
            "node_id": self.node_id,
            "message_id": msg_id,
            "timestamp": now_utc,
            "sensors": sensors
        }
        return payload

    def send_telemetry(self, payload=None, sensor_error=False):
        """Sends JSON telemetry via HTTP POST."""
        if payload is None:
            payload = self._generate_telemetry(sensor_error=sensor_error)

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.gateway_url,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                resp_data = json.loads(response.read().decode("utf-8"))
                return status_code, resp_data, payload
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_data = {"error": str(e)}
            return e.code, err_data, payload
        except Exception as e:
            return 0, {"error": str(e)}, payload


def run_simulation():
    parser = argparse.ArgumentParser(description="Simulate ESP32 Sensor Nodes sending data to Linux Gateway")
    parser.add_argument("--gateway", default="http://127.0.0.1:8080/api/v1/telemetry", help="Gateway URL")
    parser.add_argument("--count", "-n", type=int, default=5, help="Number of telemetry cycles to send (0 for infinite)")
    parser.add_argument("--interval", "-i", type=float, default=2.0, help="Interval between cycles in seconds")
    parser.add_argument("--start-seq", type=int, default=1, help="Starting sequence number for message_id")
    parser.add_argument("--test-duplicate", action="store_true", help="Send a duplicate message to test idempotency")
    parser.add_argument("--test-sensor-error", action="store_true", help="Send null sensor value to test sensor fault logic")
    parser.add_argument("--test-invalid-schema", action="store_true", help="Send invalid payload to test gateway validation")
    args = parser.parse_args()

    # Node 1: SHT3x (Temp, Hum) + PMS5003 (PM2.5)
    node1 = ESP32NodeSimulator("esp32_01", ["sht3x", "pms5003"], args.gateway, start_seq=args.start_seq)
    # Node 2: SHT3x (Temp, Hum) + SCD4x (CO2)
    node2 = ESP32NodeSimulator("esp32_02", ["sht3x", "scd4x"], args.gateway, start_seq=args.start_seq)

    print("==================================================================")
    print("        ESP32 NODE SIMULATOR FOR LINUX GATEWAY (DO AN 1)")
    print(f"  Node 1: 'esp32_01' [SHT3x: Temp, Hum | PMS5003: PM2.5] (Start Seq: {args.start_seq})")
    print(f"  Node 2: 'esp32_02' [SHT3x: Temp, Hum | SCD4x: CO2] (Start Seq: {args.start_seq})")
    print(f"  Target: {args.gateway}")
    print("==================================================================")

    # 1. Edge Case: Invalid Schema Test
    if args.test_invalid_schema:
        print("\n[TEST] Sending malformed payload (missing schema_version & node_id)...")
        bad_payload = {"temperature": 25.5}
        code, resp, _ = node1.send_telemetry(payload=bad_payload)
        print(f"  -> Gateway Response: HTTP {code} | {resp}")
        print("  -> Result: " + ("PASS (Correctly Rejected)" if code == 400 else "FAIL"))
        return

    # 2. Edge Case: Duplicate Test
    if args.test_duplicate:
        print("\n[TEST] Sending message once, then sending exact duplicate...")
        p = node1._generate_telemetry()
        # Ensure fresh unique id for duplicate test
        p["message_id"] = f"{node1.node_id}-dup-test-{int(time.time())}"
        code1, resp1, _ = node1.send_telemetry(payload=p)
        print(f"  [1st Send] HTTP {code1} | Action: {resp1.get('action')} | Msg: {p['message_id']}")
        time.sleep(0.5)
        code2, resp2, _ = node1.send_telemetry(payload=p)
        print(f"  [2nd Send - Duplicate] HTTP {code2} | Action: {resp2.get('action')} | Msg: {p['message_id']}")
        if resp2.get("action") == "duplicate_ignored" and code2 == 200:
            print("  -> Result: PASS (Gateway acknowledged idempotency without duplicate DB entry)")
        else:
            print("  -> Result: FAIL")
        return

    # Regular Simulation Cycles
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"\n--- Cycle {cycle} [{datetime.now().strftime('%H:%M:%S')}] ---")

            # Send Node 1
            code1, resp1, p1 = node1.send_telemetry(sensor_error=args.test_sensor_error)
            print(f"  Node 1 ({node1.node_id}) [{p1['message_id']}]: Temp={p1['sensors'].get('temperature_c')}°C, "
                  f"Hum={p1['sensors'].get('humidity_pct')}%, PM2.5={p1['sensors'].get('pm25_ug_m3')} µg/m³ "
                  f"-> HTTP {code1} ({resp1.get('action')})")

            # Send Node 2
            code2, resp2, p2 = node2.send_telemetry(sensor_error=args.test_sensor_error)
            print(f"  Node 2 ({node2.node_id}) [{p2['message_id']}]: Temp={p2['sensors'].get('temperature_c')}°C, "
                  f"Hum={p2['sensors'].get('humidity_pct')}%, CO2={p2['sensors'].get('co2_ppm')} ppm "
                  f"-> HTTP {code2} ({resp2.get('action')})")

            if args.count > 0 and cycle >= args.count:
                print(f"\nCompleted {cycle} simulation cycles.")
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")


if __name__ == "__main__":
    run_simulation()
