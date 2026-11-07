"""
Unit tests for Telemetry Validator (M0/M1 specification).
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.validator import validate_telemetry_payload


class TestTelemetryValidator(unittest.TestCase):

    def setUp(self):
        self.valid_payload_node1 = {
            "schema_version": 1,
            "node_id": "esp32_01",
            "message_id": "esp32_01-000001",
            "timestamp": "2026-10-16T08:00:00Z",
            "sensors": {
                "temperature_c": 28.4,
                "humidity_pct": 67.2,
                "pm25_ug_m3": 12.0
            }
        }
        self.valid_payload_node2 = {
            "schema_version": 1,
            "node_id": "esp32_02",
            "message_id": "esp32_02-000001",
            "timestamp": "2026-10-16T08:05:00Z",
            "sensors": {
                "temperature_c": 27.1,
                "humidity_pct": 65.0,
                "co2_ppm": 620.0
            }
        }

    def test_valid_node1_payload(self):
        ok, err, norm = validate_telemetry_payload(self.valid_payload_node1)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(norm["node_id"], "esp32_01")
        self.assertEqual(norm["sensors"]["temperature_c"], 28.4)
        self.assertEqual(norm["sensors"]["humidity_pct"], 67.2)
        self.assertEqual(norm["sensors"]["pm25_ug_m3"], 12.0)

    def test_valid_node2_payload(self):
        ok, err, norm = validate_telemetry_payload(self.valid_payload_node2)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(norm["node_id"], "esp32_02")
        self.assertEqual(norm["sensors"]["co2_ppm"], 620.0)

    def test_sensor_null_error_handling(self):
        # Per M1 spec: null is allowed to represent sensor read errors, never use 0 for error
        p = dict(self.valid_payload_node1)
        p["sensors"] = {"temperature_c": None, "humidity_pct": 70.0}
        ok, err, norm = validate_telemetry_payload(p)
        self.assertTrue(ok)
        self.assertIsNone(norm["sensors"]["temperature_c"])

    def test_missing_schema_version(self):
        p = dict(self.valid_payload_node1)
        del p["schema_version"]
        ok, err, _ = validate_telemetry_payload(p)
        self.assertFalse(ok)
        self.assertIn("schema_version", err)

    def test_missing_node_id(self):
        p = dict(self.valid_payload_node1)
        del p["node_id"]
        ok, err, _ = validate_telemetry_payload(p)
        self.assertFalse(ok)
        self.assertIn("node_id", err)

    def test_missing_message_id(self):
        p = dict(self.valid_payload_node1)
        del p["message_id"]
        ok, err, _ = validate_telemetry_payload(p)
        self.assertFalse(ok)
        self.assertIn("message_id", err)

    def test_empty_sensors_dict(self):
        p = dict(self.valid_payload_node1)
        p["sensors"] = {}
        ok, err, _ = validate_telemetry_payload(p)
        self.assertFalse(ok)
        self.assertIn("empty", err)

    def test_invalid_sensor_type(self):
        p = dict(self.valid_payload_node1)
        p["sensors"] = {"temperature_c": "twenty-eight"}
        ok, err, _ = validate_telemetry_payload(p)
        self.assertFalse(ok)
        self.assertIn("must be number or null", err)


if __name__ == "__main__":
    unittest.main()
