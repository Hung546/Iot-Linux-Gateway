"""
Configuration module for MYIR MYS-6ULX Gateway Daemon.
Supports default fallbacks, JSON config file, and Environment variable overrides.
"""

import os
import json
import logging

DEFAULT_CONFIG = {
    "gateway": {
        "id": "myir-mys6ulx-gw01",
        "board_model": "MYIR MYS-6ULX-IND (i.MX 6ULL Cortex-A7)",
        "db_path": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gateway.db"),
        "log_level": "INFO",
        "log_file": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "gateway.log"),
    },
    "http_server": {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 8080,
    },
    "local_mqtt_rx": {
        "enabled": False,  # Optional local broker subscriber
        "broker_host": "127.0.0.1",
        "broker_port": 1883,
        "topics": ["devices/+/telemetry", "gateway/telemetry/rx"],
    },
    "cloud_forwarder": {
        "enabled": True,
        "broker_host": "127.0.0.1",  # Local mock or thingsboard.cloud
        "broker_port": 1883,
        "username_or_token": "mys6ulx_access_token",
        "password": "",
        "topic": "v1/devices/me/telemetry",
        "batch_size": 20,
        "poll_interval_sec": 2.0,
        "retry_backoff_max_sec": 30.0,
        "mock_mode": True,  # Default to mock/simulation mode for safe local testing without cloud account
    },
    "storage": {
        "max_records": 50000,
        "retention_policy": "purge_sent_oldest",  # Keeps unsent buffer safe
        "warning_threshold_pct": 85.0,
    }
}


def load_config(config_file_path=None):
    """Loads configuration with hierarchy: Default -> File -> Environment."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # Deep copy

    if not config_file_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_file = os.path.join(base_dir, "gateway", "config.json")
        if os.path.exists(default_file):
            config_file_path = default_file

    if config_file_path and os.path.exists(config_file_path):
        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                for section, vals in file_cfg.items():
                    if section in config and isinstance(vals, dict):
                        config[section].update(vals)
                    else:
                        config[section] = vals
        except Exception as e:
            logging.warning("Failed to parse config file %s: %s. Using defaults.", config_file_path, e)

    # Environment overrides
    if "GATEWAY_HTTP_PORT" in os.environ:
        try:
            config["http_server"]["port"] = int(os.environ["GATEWAY_HTTP_PORT"])
        except ValueError:
            pass

    if "GATEWAY_DB_PATH" in os.environ:
        config["gateway"]["db_path"] = os.environ["GATEWAY_DB_PATH"]

    if "GATEWAY_MOCK_CLOUD" in os.environ:
        config["cloud_forwarder"]["mock_mode"] = os.environ["GATEWAY_MOCK_CLOUD"].lower() in ("1", "true", "yes")

    # Ensure directories exist
    db_dir = os.path.dirname(config["gateway"]["db_path"])
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    log_dir = os.path.dirname(config["gateway"]["log_file"])
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    return config
