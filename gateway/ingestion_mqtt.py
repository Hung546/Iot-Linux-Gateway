"""
Local MQTT Ingestion Subscriber for MYIR MYS-6ULX Gateway Daemon.
Subscribes to local broker topics (e.g., 'devices/+/telemetry') to receive
telemetry published by ESP32 nodes in local LAN.
"""

import time
import json
import logging
import threading

from .validator import validate_telemetry_payload

logger = logging.getLogger("gateway.mqtt_rx")

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


class LocalMQTTIngestion(threading.Thread):
    """Subscribes to local MQTT broker for incoming node messages."""

    def __init__(self, db_manager, config):
        super().__init__()
        self.daemon = True
        self.db = db_manager
        self.cfg = config.get("local_mqtt_rx", {})
        self.enabled = self.cfg.get("enabled", False)
        self.broker_host = self.cfg.get("broker_host", "127.0.0.1")
        self.broker_port = self.cfg.get("broker_port", 1883)
        self.topics = self.cfg.get("topics", ["devices/+/telemetry", "gateway/telemetry/rx"])
        
        self._running = False
        self._client = None

    def run(self):
        if not self.enabled:
            logger.info("Local MQTT Ingestion is disabled in config.")
            return

        if not PAHO_AVAILABLE:
            logger.warning("paho-mqtt library not found. Local MQTT Ingestion cannot start.")
            return

        self._running = True
        logger.info("Starting Local MQTT Ingestion connecting to %s:%d", self.broker_host, self.broker_port)

        try:
            if hasattr(mqtt, "CallbackAPIVersion"):
                self._client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id="mys6ulx_local_rx"
                )
            else:
                self._client = mqtt.Client(client_id="mys6ulx_local_rx")

            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    logger.info("Local MQTT Ingestion connected to broker.")
                    for t in self.topics:
                        client.subscribe(t, qos=1)
                        logger.info("Subscribed to local topic: %s", t)
                else:
                    logger.warning("Failed to connect to local broker, code %d", rc)

            def on_message(client, userdata, msg):
                try:
                    payload_str = msg.payload.decode("utf-8")
                    data = json.loads(payload_str)
                    
                    is_valid, err_msg, norm = validate_telemetry_payload(data)
                    if not is_valid:
                        logger.warning("Invalid MQTT telemetry received on %s: %s", msg.topic, err_msg)
                        return

                    is_new, rec_id, action = self.db.insert_telemetry(norm, payload_str, f"mqtt:{msg.topic}")
                    if is_new:
                        logger.info("Accepted MQTT telemetry from Node '%s' (msg_id: %s) -> Record #%d",
                                    norm["node_id"], norm["message_id"], rec_id)
                    else:
                        logger.info("Duplicate MQTT message ignored from Node '%s' (msg_id: %s)",
                                    norm["node_id"], norm["message_id"])

                except Exception as e:
                    logger.error("Error processing MQTT message: %s", e)

            self._client.on_connect = on_connect
            self._client.on_message = on_message

            self._client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self._client.loop_start()

            while self._running:
                time.sleep(1.0)

        except Exception as e:
            logger.warning("Local MQTT Ingestion encountered error: %s", e)

    def stop(self):
        self._running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
