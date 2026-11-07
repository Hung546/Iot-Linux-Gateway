#!/usr/bin/env python3
"""
Main Gateway System Daemon for MYIR MYS-6ULX-IND (i.MX6 Embedded Linux).
Coordinates HTTP Ingestion, MQTT Subscription, SQLite Buffer, and Store-and-Forward to Cloud.
Designed to run directly in terminal or as a systemd background service.
"""

import os
import sys
import signal
import logging
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.config import load_config
from gateway.database import DatabaseManager
from gateway.forwarder import CloudForwarder
from gateway.ingestion_http import HTTPServerManager
from gateway.ingestion_mqtt import LocalMQTTIngestion


def setup_logging(config):
    """Sets up standardized logging format suitable for terminal and systemd/journald."""
    log_level_str = config["gateway"].get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [logging.StreamHandler(sys.stdout)]

    log_file = config["gateway"].get("log_file")
    if log_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Could not open log file {log_file}: {e}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True
    )


def main():
    parser = argparse.ArgumentParser(description="MYIR MYS-6ULX Linux Gateway Daemon")
    parser.add_argument("--config", "-c", type=str, help="Path to custom config.json")
    parser.add_argument("--port", "-p", type=int, help="Override HTTP server port")
    parser.add_argument("--db", type=str, help="Override SQLite database path")
    parser.add_argument("--mock-cloud", action="store_true", help="Force mock cloud mode (offline simulation)")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.port:
        config["http_server"]["port"] = args.port
    if args.db:
        config["gateway"]["db_path"] = args.db
    if args.mock_cloud:
        config["cloud_forwarder"]["mock_mode"] = True

    setup_logging(config)
    logger = logging.getLogger("gateway.main")

    logger.info("==================================================================")
    logger.info("  MYIR MYS-6ULX-IND IOT GATEWAY DAEMON (Do An 1 - N06)")
    logger.info("  Hardware: NXP i.MX 6ULL ARM Cortex-A7 (MYS-6ULX-IND)")
    logger.info("  Gateway ID: %s", config["gateway"]["id"])
    logger.info("  Database Path: %s", config["gateway"]["db_path"])
    logger.info("  HTTP Listener: http://%s:%d", config["http_server"]["host"], config["http_server"]["port"])
    logger.info("  Cloud Mode: %s", "MOCK/STORE-AND-FORWARD SIMULATION" if config["cloud_forwarder"]["mock_mode"] else "LIVE MQTT")
    logger.info("==================================================================")

    # 1. Initialize SQLite Database
    db_manager = DatabaseManager(
        db_path=config["gateway"]["db_path"],
        max_records=config["storage"]["max_records"]
    )

    # 2. Initialize Cloud Forwarder (Store-and-Forward Worker)
    forwarder = CloudForwarder(db_manager, config)
    forwarder.start()

    # 3. Initialize Local MQTT Ingestion (if enabled)
    mqtt_rx = LocalMQTTIngestion(db_manager, config)
    if config["local_mqtt_rx"]["enabled"]:
        mqtt_rx.start()

    # 4. Initialize HTTP REST Server
    http_manager = HTTPServerManager(
        host=config["http_server"]["host"],
        port=config["http_server"]["port"],
        db_manager=db_manager,
        forwarder_ref=forwarder
    )

    # Signal handling for graceful shutdown
    def handle_signal(sig, frame):
        logger.info("Received termination signal (%d). Shutting down gateway...", sig)
        http_manager.stop()
        forwarder.stop()
        mqtt_rx.stop()
        logger.info("Gateway daemon stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        http_manager.start()
    except Exception as e:
        logger.error("Fatal error starting HTTP Ingestion server: %s", e)
        forwarder.stop()
        mqtt_rx.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
