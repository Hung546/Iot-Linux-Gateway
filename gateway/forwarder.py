"""
Store-and-Forward Cloud Forwarder for MYIR MYS-6ULX Gateway.
Manages uplink connection to ThingsBoard/Cloud MQTT platform, FIFO buffer draining,
and offline buffering resilience.
"""

import time
import json
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("gateway.forwarder")

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


class CloudForwarder(threading.Thread):
    """
    Background worker that extracts PENDING records from SQLite and forwards them
    to ThingsBoard/Cloud MQTT platform with store-and-forward semantics.
    """

    def __init__(self, db_manager, config):
        super().__init__()
        self.daemon = True
        self.db = db_manager
        self.cfg = config.get("cloud_forwarder", {})
        
        self.enabled = self.cfg.get("enabled", True)
        self.mock_mode = self.cfg.get("mock_mode", True)
        self.broker_host = self.cfg.get("broker_host", "127.0.0.1")
        self.broker_port = self.cfg.get("broker_port", 1883)
        self.token = self.cfg.get("username_or_token", "mys6ulx_access_token")
        self.topic = self.cfg.get("topic", "v1/devices/me/telemetry")
        self.batch_size = self.cfg.get("batch_size", 20)
        self.poll_interval = self.cfg.get("poll_interval_sec", 2.0)

        self._running = False
        self._is_online = not self.mock_mode or True  # Initial state
        self._mqtt_client = None
        self._cloud_connected = False
        self._forwarded_total = 0
        self._last_forward_time = None
        self._lock = threading.Lock()

    def set_online_state(self, is_online):
        """Allows test scripts to toggle online/offline simulation for M2 demo."""
        with self._lock:
            self._is_online = is_online
            logger.info(">>> Cloud connection status changed: %s <<<", "ONLINE (Connected)" if is_online else "OFFLINE (Disconnected)")

    def get_status(self):
        """Returns forwarder telemetry status."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "mock_mode": self.mock_mode,
                "is_online": self._is_online and (self._cloud_connected if not self.mock_mode else True),
                "broker_target": f"{self.broker_host}:{self.broker_port}",
                "topic": self.topic,
                "forwarded_total": self._forwarded_total,
                "last_forward_time": self._last_forward_time
            }

    def _setup_mqtt(self):
        """Initializes real Paho MQTT client if mock_mode is disabled."""
        if not PAHO_AVAILABLE:
            logger.warning("paho-mqtt not installed. Falling back to mock forwarder mode.")
            self.mock_mode = True
            return

        try:
            # Check paho callback API version (v2 vs v1)
            if hasattr(mqtt, "CallbackAPIVersion"):
                self._mqtt_client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"mys6ulx_gw_{int(time.time())}"
                )
            else:
                self._mqtt_client = mqtt.Client(client_id=f"mys6ulx_gw_{int(time.time())}")

            if self.token:
                self._mqtt_client.username_pw_set(self.token)

            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    logger.info("Connected successfully to Cloud MQTT broker at %s:%d", self.broker_host, self.broker_port)
                    self._cloud_connected = True
                else:
                    logger.warning("Cloud MQTT connection failed with code: %d", rc)
                    self._cloud_connected = False

            def on_disconnect(client, userdata, flags=None, rc=None, properties=None):
                logger.warning("Disconnected from Cloud MQTT broker (rc=%s)", rc)
                self._cloud_connected = False

            self._mqtt_client.on_connect = on_connect
            self._mqtt_client.on_disconnect = on_disconnect

            self._mqtt_client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self._mqtt_client.loop_start()

        except Exception as e:
            logger.warning("Could not establish MQTT connection to %s:%d: %s", self.broker_host, self.broker_port, e)
            self._cloud_connected = False

    def run(self):
        self._running = True
        logger.info("Cloud Forwarder started (mode=%s, poll_interval=%.1fs)",
                    "MOCK/SIMULATION" if self.mock_mode else "MQTT_LIVE", self.poll_interval)

        if not self.mock_mode:
            self._setup_mqtt()

        while self._running:
            try:
                self._process_queue_cycle()
            except Exception as e:
                logger.error("Error in Cloud Forwarder cycle: %s", e, exc_info=True)

            time.sleep(self.poll_interval)

    def _process_queue_cycle(self):
        """Fetches pending batch and forwards if uplink is available."""
        if not self.enabled:
            return

        with self._lock:
            currently_online = self._is_online

        if not currently_online:
            # Network outage: buffering locally
            logger.debug("Cloud uplink currently OFFLINE. Data buffered locally in SQLite.")
            return

        # Fetch FIFO batch of pending telemetry
        batch = self.db.get_pending_records(limit=self.batch_size)
        if not batch:
            return

        logger.info("Draining store-and-forward buffer: found %d pending records to forward...", len(batch))

        sent_ids = []
        for record in batch:
            success = self._forward_record(record)
            if success:
                sent_ids.append(record["id"])
            else:
                self.db.mark_records_failed([record["id"]], "Uplink delivery error")
                # Break batch early if connection broke mid-batch
                break

        if sent_ids:
            self.db.mark_records_as_sent(sent_ids)
            with self._lock:
                self._forwarded_total += len(sent_ids)
                self._last_forward_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info("Successfully delivered %d buffered records to Cloud. Total sent: %d",
                        len(sent_ids), self._forwarded_total)

    def _forward_record(self, record):
        """Formats and publishes single record to Cloud/ThingsBoard."""
        # Convert timestamp to epoch ms for ThingsBoard API
        try:
            ts_str = record["timestamp"].rstrip("Z")
            dt = datetime.fromisoformat(ts_str)
            ts_ms = int(dt.timestamp() * 1000)
        except Exception:
            ts_ms = int(time.time() * 1000)

        # ThingsBoard telemetry structure with custom timestamp
        values_dict = {
            "node_id": record["node_id"],
            "message_id": record["message_id"],
        }
        if record["temperature_c"] is not None:
            values_dict["temperature"] = record["temperature_c"]
        if record["humidity_pct"] is not None:
            values_dict["humidity"] = record["humidity_pct"]
        if record["pm25_ug_m3"] is not None:
            values_dict["pm25"] = record["pm25_ug_m3"]
        if record["co2_ppm"] is not None:
            values_dict["co2"] = record["co2_ppm"]

        cloud_payload = {
            "ts": ts_ms,
            "values": values_dict
        }

        payload_json = json.dumps(cloud_payload)

        if self.mock_mode:
            # Mock mode: successfully simulated cloud receipt
            logger.debug("[MOCK CLOUD] Published to topic '%s': %s", self.topic, payload_json)
            return True
        else:
            if not self._cloud_connected or not self._mqtt_client:
                return False
            try:
                info = self._mqtt_client.publish(self.topic, payload_json, qos=1)
                info.wait_for_publish(timeout=3.0)
                return info.is_published()
            except Exception as e:
                logger.warning("Failed to publish to MQTT: %s", e)
                return False

    def stop(self):
        logger.info("Stopping Cloud Forwarder...")
        self._running = False
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
