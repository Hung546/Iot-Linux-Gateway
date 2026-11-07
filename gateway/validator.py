"""
Telemetry Payload Validator according to Milestone M0 & M1 Specifications.
Validates JSON structure, required fields, data types, and sensor ranges.
"""

import re
from datetime import datetime

# Known valid sensor fields in Do An 1
KNOWN_SENSORS = {
    "temperature_c": {"min": -40.0, "max": 85.0, "unit": "°C"},
    "humidity_pct": {"min": 0.0, "max": 100.0, "unit": "%"},
    "pm25_ug_m3": {"min": 0.0, "max": 1000.0, "unit": "µg/m³"},
    "co2_ppm": {"min": 300.0, "max": 10000.0, "unit": "ppm"},
}


class ValidationError(Exception):
    """Raised when incoming JSON payload violates M0/M1 specification."""
    pass


def parse_iso8601_timestamp(ts_str):
    """Validates and parses ISO 8601 timestamp string (e.g. 2026-10-16T08:00:00Z)."""
    if not isinstance(ts_str, str):
        raise ValidationError(f"timestamp must be a string, got {type(ts_str).__name__}")
    
    # Try common formats
    clean_ts = ts_str.strip()
    # Replace 'Z' with '+00:00' for fromisoformat compatibility in python 3.10+
    if clean_ts.endswith("Z"):
        clean_ts = clean_ts[:-1] + "+00:00"
    
    try:
        dt = datetime.fromisoformat(clean_ts)
        return dt
    except ValueError:
        pass
    
    # Fallback parsing
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts_str.rstrip("Z"), fmt)
        except ValueError:
            continue
            
    raise ValidationError(f"Invalid timestamp format '{ts_str}'. Expected ISO 8601 (e.g. 2026-10-16T08:00:00Z)")


def validate_telemetry_payload(data):
    """
    Validates telemetry payload dictionary.
    Returns:
        tuple (is_valid: bool, error_message: str or None, normalized_data: dict)
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object", {}

    # 1. schema_version check
    if "schema_version" not in data:
        return False, "Missing required field: 'schema_version'", {}
    if not isinstance(data["schema_version"], int) or data["schema_version"] < 1:
        return False, f"Invalid 'schema_version': {data.get('schema_version')} (must be integer >= 1)", {}

    # 2. node_id check
    node_id = data.get("node_id")
    if not node_id or not isinstance(node_id, str) or not node_id.strip():
        return False, "Missing or invalid field: 'node_id' (must be a non-empty string)", {}
    node_id = node_id.strip()

    # 3. message_id check (crucial for deduplication & idempotency)
    message_id = data.get("message_id")
    if not message_id or not isinstance(message_id, str) or not message_id.strip():
        return False, "Missing or invalid field: 'message_id' (must be a non-empty unique string)", {}
    message_id = message_id.strip()

    # 4. timestamp check
    ts_raw = data.get("timestamp")
    if not ts_raw:
        return False, "Missing required field: 'timestamp'", {}
    try:
        dt = parse_iso8601_timestamp(ts_raw)
        standardized_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValidationError as ve:
        return False, str(ve), {}

    # 5. sensors object check
    sensors = data.get("sensors")
    if not isinstance(sensors, dict):
        return False, "Missing or invalid field: 'sensors' (must be a dictionary)", {}

    if len(sensors) == 0:
        return False, "'sensors' dictionary cannot be empty", {}

    normalized_sensors = {}
    validation_warnings = []

    for key, val in sensors.items():
        if key not in KNOWN_SENSORS:
            # Unknown sensor key: we allow with warning for future sensor expansion
            validation_warnings.append(f"Unknown sensor key: {key}")
            normalized_sensors[key] = val
            continue

        if val is None:
            # Explicit null represents a sensor reading failure (per spec)
            normalized_sensors[key] = None
            continue

        if not isinstance(val, (int, float)):
            return False, f"Sensor value for '{key}' must be number or null, got {type(val).__name__}", {}

        val_float = float(val)
        limits = KNOWN_SENSORS[key]
        if val_float < limits["min"] or val_float > limits["max"]:
            validation_warnings.append(
                f"Sensor '{key}' value {val_float} is outside plausible range [{limits['min']}, {limits['max']}] {limits['unit']}"
            )
        normalized_sensors[key] = val_float

    normalized_data = {
        "schema_version": data["schema_version"],
        "node_id": node_id,
        "message_id": message_id,
        "timestamp": standardized_timestamp,
        "sensors": normalized_sensors,
        "warnings": validation_warnings
    }

    return True, None, normalized_data
